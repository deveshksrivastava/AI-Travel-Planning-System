# Free Deployment: Streamlit Community Cloud + Neon

Deploy this app for **$0** using:

| Need | Free service |
|---|---|
| Host the Streamlit app | [Streamlit Community Cloud](https://share.streamlit.io) |
| PostgreSQL (checkpointer memory) | [Neon](https://neon.tech) free tier |
| MCP server | Nothing extra — spawned as a subprocess inside the app |
| LLM + search APIs | Your existing Groq / Tavily / AviationStack keys |

The repo is already prepared: `requirements.txt` is committed, `frontend.py`
loads keys from Streamlit Secrets, and `main.py` passes the API keys through
to the MCP subprocess. You only need the account steps below (~10 minutes).

---

## Step 1 — Create a free Neon Postgres database

1. Go to <https://neon.tech> → **Sign up** (GitHub login works; no card needed).
2. Create a project (any name, e.g. `langgraph-travel`). Pick the region
   closest to you.
3. On the project dashboard, click **Connect** and copy the **connection
   string**. Choose the **direct (non-pooled)** connection if offered — the
   LangGraph checkpointer manages its own connection pool.
   It looks like:
   ```
   postgresql://USER:PASSWORD@ep-xxx-xxx.region.aws.neon.tech/neondb?sslmode=require
   ```
4. That's it — `PostgresSaver.setup()` creates its own tables on first run.
   No manual `CREATE DATABASE` needed.

## Step 2 — Deploy on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> → **Sign in with GitHub**
   (authorize access to your repos).
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `deveshksrivastava/AI-Travel-Planning-System-using-LangGraph`
   - **Branch:** `main` (or the branch holding these deployment files)
   - **Main file path:** `frontend.py`
   - **App URL:** pick a subdomain, e.g. `ai-travel-planner`
4. Click **Advanced settings**:
   - **Python version:** `3.13`
   - **Secrets:** paste the block below with your real values:
     ```toml
     GROQ_API_KEY = "gsk_..."
     TAVILY_API_KEY = "tvly-..."
     AVIATIONSTACK_API_KEY = "..."
     DATABASE_URL = "postgresql://USER:PASSWORD@ep-xxx.region.aws.neon.tech/neondb?sslmode=require"
     ```
5. Click **Deploy**. First build takes a few minutes (installs
   `requirements.txt`). When it goes green, your app is live at
   `https://<your-subdomain>.streamlit.app`.

## Step 3 — Smoke test

1. Open the app URL, enter a trip query (e.g. *"Paris trip for 5 days"*),
   click **Generate My Travel Plan**.
2. All four agent cards should fill in. The human-review step is
   auto-approved in the web UI (interactive review is CLI-only).
3. If something fails, open **Manage app → Logs** (bottom-right of the app
   page) — missing/typo'd secrets are the most common cause.

---

## Known free-tier limits (fine for a demo)

- **App sleeps** after ~12 h with no visitors; first visit after that takes
  ~30 s to wake.
- **AviationStack free tier = 100 requests/month** — flight search will start
  returning errors once exhausted; hotels + itinerary keep working.
- **Neon free tier** auto-suspends compute when idle; first query after idle
  adds ~1 s. Storage limit is generous for checkpointer data.
- `travel_plans/` files saved by the app live on ephemeral storage and
  disappear on restart — use the **Download Plan** button instead.

## Updating the deployed app

Just `git push` to the deployed branch — Streamlit Cloud redeploys
automatically. To change secrets: app page → **Settings → Secrets**.

## Notes

- **Never commit `.env` or secrets.toml** — secrets belong only in the
  Streamlit Secrets panel (already verified: `.env` has never been in git
  history, and `.gitignore` covers it).
- Runner-up host if you outgrow Streamlit Cloud:
  [Hugging Face Spaces](https://huggingface.co/spaces) (also free,
  Streamlit-compatible).
