# Production Readiness Plan — AI Travel Planning System

> **Verdict (today): NOT production-ready.** This is a well-built *prototype /
> learning project*. It runs and demos nicely, but it would fail under real
> multi-user load and is missing the fundamentals (auth, error handling,
> pooling, observability, tests, deployment). This document explains exactly
> what's missing and gives a concrete, phased plan to get it to production for
> hundreds of concurrent users.

---

## 1. Current State Assessment

### What already works (the good parts)
- Clean LangGraph multi-agent pipeline (`flight → hotel → itinerary → final`).
- Shared `TravelState`, PostgreSQL checkpointer for per-thread memory.
- Two interfaces (CLI + a polished Streamlit UI).
- Secrets removed from git; `.gitignore` + `.env.example` in place.
- Good documentation (`learn-graph.md`, `learn-crewai.md`, `learn-autogen.md`, README diagrams).

### Maturity rating

| Area | Status | Score (1–5) |
|---|---|---|
| Core feature works end-to-end | Partly (flight search is broken) | 2 |
| Error handling & resilience | Missing | 1 |
| Concurrency / scalability | Single connection, blocking | 1 |
| Authentication & multi-tenancy | None | 1 |
| Observability (logs/traces/metrics) | None | 1 |
| Testing | None | 1 |
| Security | Basic (secrets handled) | 2 |
| Deployment / CI-CD | None | 1 |
| Cost & rate controls | None | 1 |
| Documentation | Strong | 4 |

**Overall: ~1.5 / 5 — prototype stage.**

---

## 2. Bugs & Gaps Found in the Current Code

These are specific, verified issues in the existing files.

### Correctness bugs
1. **Flight search ignores the user's query** — `tools/flight_tool.py` only sends
   `access_key` + `limit=5` to AviationStack. It returns 5 random global flights,
   not flights for the requested route/dates. The flight agent is effectively
   non-functional.
2. **No error handling on external calls** — `flight_tool.py` and `tavily_tool.py`
   call the APIs with no timeout, no HTTP status check, and no `try/except`.
   A single API error crashes the entire graph run.
3. **State/UI mismatch** — `frontend.py` reads a `final_response` key that the
   graph state never declares (`TravelState` has no `final_response`). It works
   only because the final agent happens to write `messages`.
4. **Itinerary/final agents don't actually use structured data** — they pass raw
   strings into prompts; no validation that flight/hotel data is non-empty.

### Concurrency / scale blockers
5. **Single global DB connection** — `main.py` opens one `psycopg.connect(...)`
   at import time and shares it process-wide. Not thread-safe; no pooling.
   Streamlit imports `main`, so every session shares this one connection.
6. **`checkpointer.setup()` runs on every import** — wasteful and racy under
   concurrent startup.
7. **Synchronous, blocking pipeline** — each request blocks on ~2 external API
   calls + ~2 LLM calls (10–30s). Streamlit serves these on a limited thread
   pool; hundreds of concurrent users will queue and time out.
8. **Local-disk persistence** — `travel_plans/` writes files to the local
   filesystem. This breaks on multi-instance / containerized / serverless
   deploys (each instance has its own disk).

### Security / multi-tenancy
9. **No authentication** — `thread_id` is a free-text field. Any user can read
   another user's saved memory simply by typing their ID. No isolation.
10. **No input validation or prompt-injection protection** — user text flows
    straight into LLM prompts.
11. **No output moderation** — model output is rendered with
    `unsafe_allow_html=True` in places, a potential XSS vector if model output
    is ever reflected as HTML.

### Operational gaps
12. **No rate limiting or cost controls** — unlimited LLM + API calls per user.
    Free-tier API quotas (AviationStack, Tavily, Groq) will be exhausted fast.
13. **No retries / backoff / circuit breakers** on flaky external calls.
14. **No logging, tracing, or metrics** — no LangSmith, no request IDs, no way
    to debug a failed run in production.
15. **Zero automated tests.**
16. **No CI/CD, no Dockerfile, no infrastructure-as-code.**
17. **Model is hardcoded** (`llama-3.3-70b-versatile`) with no fallback,
    no timeout, no token/cost budget.

---

## 3. Things to Change in This Project (concrete, near-term)

These are high-value changes that fit the current codebase without a rewrite:

1. **Fix the flight tool** — pass the actual route/dates to AviationStack (or use
   a real flight API), and parse the user query into structured params (origin,
   destination, date) using the LLM before calling the API.
2. **Add timeouts + try/except + retries** to every external call
   (`requests.get(..., timeout=10)`, `tenacity` for retries).
3. **Replace the global connection with a pool** — use
   `PostgresSaver.from_conn_string()` with a `ConnectionPool`
   (`psycopg_pool`), and run `setup()` once at startup (migration step), not on
   every import.
4. **Move `setup()` out of import path** — make graph building a function
   (`build_app()`), call DB migration explicitly in a startup hook.
5. **Make flight + hotel run in parallel** — they're independent. Use LangGraph
   fan-out (both from START) and join before the itinerary agent. Roughly halves
   latency.
6. **Add structured logging** (Python `logging` + JSON formatter) and a
   per-request correlation/thread ID.
7. **Add LangSmith tracing** (`LANGCHAIN_TRACING_V2=true`) for agent-step
   visibility.
8. **Externalize persistence of saved plans** — write to PostgreSQL or object
   storage (S3/GCS) instead of `travel_plans/` on local disk.
9. **Add a config layer** — a `Settings` class (e.g. `pydantic-settings`) that
   validates required env vars at startup and fails fast if missing.
10. **Add input validation & length limits** on user queries; sanitize before
    prompting.
11. **Pin dependencies** — add a `requirements.txt` / `pyproject.toml` with
    pinned versions (currently install commands are inline in the README).

---

## 4. Productionization Plan (for hundreds of concurrent users)

The core architectural shift: **separate the UI from the agent backend**, make
the backend **async and horizontally scalable**, and **offload long-running
agent runs to a job queue** so requests don't block.

### Target Architecture

```text
                    ┌──────────────┐
   Users  ───────▶  │   Web UI     │  (Next.js / React, or Streamlit behind auth)
                    │  + Auth      │
                    └──────┬───────┘
                           │ HTTPS / JWT
                    ┌──────▼───────┐
                    │  API Gateway │  (rate limiting, auth, WAF)
                    └──────┬───────┘
                    ┌──────▼───────┐        ┌───────────────┐
                    │  FastAPI     │───────▶│  Job Queue    │  (Redis / Celery
                    │  (async)     │        │  + Workers    │   or RQ / Arq)
                    └──────┬───────┘        └──────┬────────┘
                           │                       │ run LangGraph
              ┌────────────┼───────────────┐       ▼
        ┌─────▼─────┐ ┌────▼─────┐  ┌───────▼────────┐
        │ Postgres  │ │  Redis   │  │ External APIs  │
        │ (pooled,  │ │ (cache,  │  │ Groq/Tavily/   │
        │ checkpt.) │ │ sessions)│  │ AviationStack  │
        └───────────┘ └──────────┘  └────────────────┘
                           │
                   ┌───────▼────────┐
                   │ Observability  │ (LangSmith, OpenTelemetry,
                   │ Logs/Traces/   │  Prometheus/Grafana, Sentry)
                   │ Metrics        │
                   └────────────────┘
```

### Phase 0 — Stabilize the prototype (1 week)
- Fix the flight tool and all correctness bugs (Section 2).
- Add timeouts, retries, and try/except to external calls.
- Add `requirements.txt` with pinned versions.
- Add a `Settings`/config module with fail-fast validation.
- Add structured logging.
- **Exit criteria:** a single user can run any query reliably without crashes.

### Phase 1 — Backend separation & API (1–2 weeks)
- Build a **FastAPI** backend exposing:
  - `POST /plan` → enqueue a planning job, return `job_id`.
  - `GET /plan/{job_id}` → poll status / stream results (SSE/WebSocket).
- Move graph construction into `build_app()`; run DB `setup()` once at startup.
- Replace the global connection with a **`psycopg_pool.ConnectionPool`**.
- Make agents **async** where possible; run flight + hotel in **parallel**.
- **Exit criteria:** backend handles concurrent requests via a connection pool;
  UI talks to it over HTTP.

### Phase 2 — Async jobs & scale (1–2 weeks)
- Add **Redis + a task queue** (Celery / RQ / Arq). Long agent runs execute in
  worker processes, not the request thread.
- Add **caching** (Redis) for repeated/expensive lookups (hotel searches, etc.).
- Stream agent progress to the UI via **Server-Sent Events / WebSockets**.
- Move saved plans to **PostgreSQL or object storage** (S3/GCS).
- **Exit criteria:** requests return immediately with a job id; workers scale
  horizontally; no request blocks on agent execution.

### Phase 3 — Security & multi-tenancy (1 week)
- Add **authentication** (OAuth/OIDC, e.g. Auth0/Clerk/Supabase Auth or JWT).
- Derive `thread_id` from the **authenticated user id** (no free-text). Enforce
  per-user data isolation at the query layer.
- Add **rate limiting** (per-user and global) at the gateway.
- Add **input validation, prompt-injection guards, and output sanitization**.
- Store secrets in a **secrets manager** (AWS Secrets Manager / GCP Secret
  Manager / Vault), not `.env`.
- **Exit criteria:** users only see their own data; abuse is rate-limited;
  secrets are managed.

### Phase 4 — Observability & cost control (1 week)
- **Tracing:** LangSmith for agent steps + OpenTelemetry for HTTP/DB.
- **Metrics:** Prometheus + Grafana (latency, error rate, queue depth, tokens).
- **Errors:** Sentry for exceptions.
- **Cost guardrails:** token budgets per request/user, model fallback
  (e.g. cheaper model on overflow), and per-user LLM/API quotas.
- **Exit criteria:** every request is traceable; alerts fire on errors/cost
  spikes.

### Phase 5 — Deployment & CI/CD (1 week)
- **Containerize** (Dockerfile for API + workers).
- **CI:** GitHub Actions — lint, type-check, tests, build image.
- **CD:** deploy to a managed platform (Render / Railway / Fly.io / AWS ECS /
  GCP Cloud Run / Kubernetes) with **autoscaling**.
- **Managed Postgres** (RDS / Cloud SQL / Supabase / Neon) with backups.
- Health checks, readiness/liveness probes, blue-green or rolling deploys.
- **Exit criteria:** push-to-deploy; the system autoscales under load.

### Phase 6 — Hardening & launch (ongoing)
- **Load testing** (Locust / k6) to validate "hundreds of concurrent users."
- **Test suite:** unit (tools, agents), integration (graph), e2e (API), with
  external APIs mocked.
- **Runbooks**, on-call alerts, SLOs, and a rollback plan.
- **Exit criteria:** load test passes target concurrency within latency/error
  SLOs.

---

## 5. Production-Readiness Checklist

Use this as the definition of "done."

- [ ] All correctness bugs fixed (flight tool, error handling, state schema)
- [ ] Every external call has timeout + retry + error handling
- [ ] DB access uses a connection pool; `setup()` runs once at startup
- [ ] Flight + hotel agents run in parallel
- [ ] Backend (FastAPI) separated from UI
- [ ] Long agent runs offloaded to a job queue + workers
- [ ] Saved plans stored in DB/object storage (not local disk)
- [ ] Authentication enforced; `thread_id` derived from authenticated user
- [ ] Per-user data isolation verified
- [ ] Rate limiting (per-user + global)
- [ ] Input validation + prompt-injection guarding + output sanitization
- [ ] Secrets in a secrets manager
- [ ] Structured logging with correlation IDs
- [ ] Tracing (LangSmith) + metrics (Prometheus/Grafana) + errors (Sentry)
- [ ] Token/cost budgets and model fallback
- [ ] Pinned dependencies (`requirements.txt`/`pyproject.toml`)
- [ ] Dockerized; CI runs lint + types + tests; CD deploys automatically
- [ ] Managed Postgres with automated backups
- [ ] Autoscaling configured
- [ ] Load tested at target concurrency within SLOs
- [ ] Test coverage: unit + integration + e2e
- [ ] Health checks, alerts, runbooks, rollback plan

---

## 6. Recommended Tech Choices

| Concern | Recommended |
|---|---|
| API backend | FastAPI (async) |
| Job queue | Celery or Arq + Redis |
| Cache / sessions | Redis |
| DB | Managed PostgreSQL (Neon / Supabase / RDS / Cloud SQL) |
| DB pooling | `psycopg_pool.ConnectionPool` |
| Auth | Clerk / Auth0 / Supabase Auth (OIDC + JWT) |
| Frontend | Keep Streamlit for internal/demo; Next.js for public scale |
| Tracing | LangSmith + OpenTelemetry |
| Metrics | Prometheus + Grafana |
| Errors | Sentry |
| Secrets | Cloud Secret Manager / Vault |
| Container/Deploy | Docker + Cloud Run / Fly.io / ECS / K8s |
| CI/CD | GitHub Actions |
| Load testing | k6 / Locust |

---

## 7. Bottom Line

- **Is it production-ready today?** No. It is a strong prototype with a clean
  architecture and good docs, but it lacks the resilience, concurrency, security,
  observability, and deployment foundations required for real users.
- **Can it get there?** Yes — the LangGraph core is sound. The realistic path is
  **~6–8 weeks** of focused work following the phased plan above, with Phase 0–2
  delivering the biggest reliability/scale gains.
- **Smallest first step:** fix the flight tool + add error handling + a DB
  connection pool (Phase 0–1). That alone moves it from "demo" to "reliable
  single-tenant app."
