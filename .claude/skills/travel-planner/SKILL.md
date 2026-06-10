---
name: travel-planner
description: Use when running, debugging, or extending this LangGraph multi-agent travel planning system - covers the agent pipeline, state, tools, env setup, and how to add or modify agents safely.
---

# Travel Planner (LangGraph Multi-Agent)

This skill helps you work with the AI Travel Planning System in this repository.

## Architecture

A sequential LangGraph pipeline sharing a `TravelState`:

```
START → flight_agent → hotel_agent → itinerary_agent → final_agent → END
```

| Agent | Source | Backed by |
|---|---|---|
| `flight_agent` | `main.py` → `tools/flight_tool.py` | AviationStack API |
| `hotel_agent` | `main.py` → `tools/tavily_tool.py` | Tavily Search API |
| `itinerary_agent` | `main.py` | Groq `llama-3.3-70b-versatile` |
| `final_agent` | `main.py` | Groq `llama-3.3-70b-versatile` |

State lives in `TravelState` (TypedDict). Memory is persisted per `thread_id`
via `PostgresSaver`.

## Setup checklist

1. Activate the venv: `source langgraph_env3/bin/activate`
2. Ensure `.env` exists (copy from `.env.example`) with `GROQ_API_KEY`,
   `TAVILY_API_KEY`, `AVIATIONSTACK_API_KEY`, `DATABASE_URL`.
3. Ensure PostgreSQL is running and the database exists.

## Common tasks

### Run it
- CLI: `python main.py`
- Web UI: `streamlit run frontend.py`
- MCP server: `python mcp_server/travel_mcp.py`

### Add a new agent
1. Write `def my_agent(state: TravelState) -> dict:` in `main.py`. Return only
   the state keys it updates (e.g. `{"hotel_results": ..., "llm_calls": ...}`).
2. `graph.add_node("my_agent", my_agent)`
3. Wire edges with `graph.add_edge(...)`.
4. If new data is produced, add the field to `TravelState`.
5. Add an entry to `AGENT_META` in `frontend.py` for the UI label/icon.

### Add a new tool
- Put it in `tools/`, give it a clear docstring, **always** add a timeout and
  `try/except` around the network call (the existing tools lack this — don't
  copy that gap), and return a string.

## Guardrails (read before editing)

- **Never** print, commit, or paste the contents of `.env`. Use `.env.example`.
- `PostgresSaver.setup()` needs an **autocommit** connection.
- `frontend.py` imports `app` from `main.py`; the graph (and `setup()`) runs at
  import time. Avoid adding heavy import-time side effects.
- Before large/architectural changes, read `PRODUCTION_READINESS.md` — it lists
  known bugs (e.g. `search_flights` ignores the query; single global DB
  connection) and the intended production direction.

## Verify your change

- Run `python main.py` with a sample prompt and confirm all four agents run
  without an exception.
- For UI changes, run `streamlit run frontend.py` and confirm the agent steps
  render and a plan is produced.
