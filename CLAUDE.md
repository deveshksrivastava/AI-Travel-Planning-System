# CLAUDE.md

Guidance for Claude Code (and other AI assistants) when working in this repository.

## Project Overview

A **multi-agent AI travel planning system** built with **LangGraph**. Four
agents run sequentially, sharing a `TravelState`, to produce a complete trip
plan (flights → hotels → itinerary → final response). Memory is persisted in
PostgreSQL via LangGraph's `PostgresSaver` checkpointer.

There are two entry points and three learning guides (LangGraph / CrewAI /
AutoGen) plus a production plan.

## Architecture

```
START → flight_agent → hotel_agent → human_review ⏸ → itinerary_agent → final_agent → END
                            ▲              │
                            └── feedback ──┘   (approve → continue)
```

- `flight_agent` / `hotel_agent` → **MCP server** (`mcp_server/travel_mcp.py`,
  spawned over stdio via `langchain-mcp-adapters`; see `call_mcp()` in `main.py`)
- `human_review` → human-in-the-loop: `interrupt()` pauses the run; resume with
  `Command(resume="approve")` or feedback text (loops back to search)
- `itinerary_agent` / `final_agent` → Groq LLM (`llama-3.3-70b-versatile`)
- State: `TravelState` (TypedDict) in `main.py`
- Memory: `PostgresSaver` (connection pool) keyed by `thread_id`
- Full guide: `human-in-loop-with-mcp.md`; minimal demo: `src/mcp_hitl_demo.py`

## Key Files

| File | Purpose |
|---|---|
| `main.py` | Graph definition, agents, MCP client, checkpointer, CLI entry point |
| `frontend.py` | Streamlit web UI (streams agent steps live; auto-approves the review pause) |
| `mcp_server/travel_mcp.py` | MCP server exposing the travel tools (the agents' tool backend) |
| `src/mcp_hitl_demo.py` | Minimal standalone demo of MCP + human-in-the-loop |
| `human-in-loop-with-mcp.md` | Guide to the MCP + HITL implementation |
| `tools/flight_tool.py` | AviationStack flight search (legacy direct-call version; MCP server has its own copy) |
| `tools/tavily_tool.py` | Tavily hotel/web search (legacy direct-call version; MCP server has its own copy) |
| `.claude/skills/travel-planner/SKILL.md` | Skill for running/extending the system |
| `learn-graph.md` / `learn-crewai.md` / `learn-autogen.md` | Framework tutorials (same example) |
| `PRODUCTION_READINESS.md` | Production assessment + scaling plan |

## Running

```bash
# Activate the virtualenv first
source langgraph_env3/bin/activate      # macOS/Linux

python main.py                          # CLI
streamlit run frontend.py               # Web UI
python mcp_server/travel_mcp.py         # MCP server (stdio)
```

## Environment

Copy `.env.example` → `.env` and fill in:
`GROQ_API_KEY`, `TAVILY_API_KEY`, `AVIATIONSTACK_API_KEY`, `DATABASE_URL`.
PostgreSQL must be running and the database created (see README Step 4).

## Conventions & Gotchas

- **Never commit `.env`** — secrets are git-ignored; use `.env.example` for keys.
- `PostgresSaver.setup()` requires an **autocommit** connection; `main.py` uses
  a `ConnectionPool` with `check_connection` so stale connections self-heal.
- `frontend.py` imports `app` from `main.py`, which builds the graph at import
  time (runs `setup()` AND `mcp_client.get_tools()`). Be careful changing
  import-time side effects.
- MCP is async; the graph is sync — always go through `call_mcp()` (it bridges
  with `asyncio.run` and flattens MCP content-block lists into strings).
- `interrupt()` requires a checkpointer; every run pauses at `human_review`.
  Any new caller of `app` must handle the `"__interrupt__"` key and resume
  with `Command(resume=...)` (see the CLI loop in `main.py` or the
  auto-approve loop in `frontend.py`).
- Known issues and the path to production are documented in
  `PRODUCTION_READINESS.md` — consult it before large changes. Notably:
  `search_flights` still ignores the user query (no IATA codes passed).

## When Adding a New Agent

1. Add a node function `def my_agent(state: TravelState) -> dict` in `main.py`.
2. Register it: `graph.add_node("my_agent", my_agent)`.
3. Wire edges: `graph.add_edge("prev", "my_agent")` / `graph.add_edge("my_agent", "next")`.
4. If it adds new state, extend the `TravelState` TypedDict.
5. Update `frontend.py`'s `AGENT_META` so the UI shows the new step.

## Safety

- This is a learning/demo project. Do not add real payment, booking, or PII
  handling without first implementing the auth, validation, and security items
  in `PRODUCTION_READINESS.md`.
