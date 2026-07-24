# Human-in-the-Loop with MCP: How This Project Uses Both

This guide explains the two upgrades made to the travel planning system:

1. **MCP (Model Context Protocol)** — agents now call tools through a separate
   MCP server process instead of importing Python functions directly.
2. **Human-in-the-Loop (HITL)** — the graph pauses mid-run so a human can
   approve the search results or send feedback before the itinerary is built.

Start with the small demo (`src/mcp_hitl_demo.py`), then read how the same
patterns are wired into the full app (`main.py` + `frontend.py`).

---

## 1. What is MCP?

MCP is an open protocol that lets an AI application call tools that live in a
**separate process** (an "MCP server"). The client and server talk over a
transport — here, **stdio** (the client launches the server as a subprocess
and exchanges JSON-RPC messages over stdin/stdout).

### Before vs after in this project

```text
BEFORE (direct import):

    main.py ──python import──> tools/flight_tool.py::search_flights()
    main.py ──python import──> tools/tavily_tool.py::tavily_search()

AFTER (MCP):

    main.py ──MCP protocol (stdio)──> mcp_server/travel_mcp.py  (separate process)
                                          ├── search_flights   (AviationStack)
                                          ├── search_hotels    (Tavily)
                                          └── plan_trip
```

### Why bother?

| Benefit | Meaning |
|---|---|
| **Decoupling** | Tool code runs in its own process; the graph only knows tool names + schemas |
| **Reusability** | The same server already works with Claude Desktop / Claude Code — now the graph uses it too |
| **One source of truth** | Tool logic, timeouts, and error handling live in one place (`mcp_server/travel_mcp.py`) |
| **Swappable** | Point the client at a different server (or a remote one) without touching agent code |

---

## 2. Connecting to the MCP server (the client side)

`langchain-mcp-adapters` does the heavy lifting: it launches the server,
discovers its tools, and converts each one into a normal LangChain tool.

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

mcp_client = MultiServerMCPClient(
    {
        "travel": {
            "command": sys.executable,                  # this venv's python
            "args": ["mcp_server/travel_mcp.py"],       # how to launch the server
            "transport": "stdio",
        }
    }
)

# Discover the server's tools (async API)
mcp_tools = {t.name: t for t in asyncio.run(mcp_client.get_tools())}
# -> {'search_flights': ..., 'search_hotels': ..., 'plan_trip': ...}
```

### Two gotchas (both handled in `call_mcp`)

1. **MCP is async, the graph is sync.** Every tool call is a coroutine, so we
   bridge with `asyncio.run(...)`.
2. **MCP tools return a LIST of content blocks**, not a plain string. The
   helper joins the text parts:

```python
def call_mcp(tool_name: str, args: dict) -> str:
    result = asyncio.run(mcp_tools[tool_name].ainvoke(args))
    if isinstance(result, list):                 # MCP content blocks
        result = "\n".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in result
        )
    return result
```

Agents then call tools like this:

```python
flight_data  = call_mcp("search_flights", {"limit": 5})
hotel_results = call_mcp("search_hotels", {"query": query, "max_results": 5})
```

---

## 3. What is Human-in-the-Loop?

HITL means the graph **pauses itself mid-run**, hands control to a human, and
resumes with whatever the human decides. LangGraph implements this with two
pieces:

| Piece | Role |
|---|---|
| `interrupt(payload)` | Called inside a node. Suspends the run, saves all state to the checkpointer, and surfaces `payload` to the caller |
| `Command(resume=answer)` | Passed to `app.invoke()` / `app.stream()` to resume. The interrupted node **re-runs**, and this time `interrupt()` returns `answer` |

**A checkpointer is required** — the paused state must be stored somewhere.
The demo uses `InMemorySaver`; the real app already had `PostgresSaver`, so
paused runs survive even a process restart.

---

## 4. The new pipeline

```text
START
  |
  v
flight_agent        (MCP: search_flights)
  |
  v
hotel_agent         (MCP: search_hotels)
  |
  v
human_review        <-- interrupt(): graph PAUSES here
  |         \
  | approve  \ feedback ("find cheaper hotels")
  v           \
itinerary_agent  --> back to flight_agent with refined query
  |
  v
final_agent
  |
  v
END
```

The human can loop as many times as needed: every piece of feedback is
appended to `user_query` and the search re-runs; `approve` moves on.

---

## 5. The HITL code, step by step

### 5.1 The pausing node

```python
from langgraph.types import interrupt

def human_review(state: TravelState):
    answer = interrupt({                         # <-- run STOPS here
        "question": "Approve these search results, or give feedback to search again.",
        "flight_results": state["flight_results"],
        "hotel_results": state["hotel_results"],
    })
    # ...when resumed, the node re-runs and `answer` holds the human's reply

    if str(answer).strip().lower() == "approve":
        return {"approved": True}

    return {                                     # feedback -> refine and re-search
        "approved": False,
        "user_query": f"{state['user_query']} (user feedback: {answer})",
    }
```

### 5.2 The conditional edge (router)

```python
def route_after_review(state: TravelState) -> str:
    return "itinerary_agent" if state["approved"] else "flight_agent"

graph.add_edge("hotel_agent", "human_review")
graph.add_conditional_edges("human_review", route_after_review,
                            ["flight_agent", "itinerary_agent"])
```

### 5.3 The caller loop (CLI)

While paused, the result of `invoke()` contains a special `"__interrupt__"`
key holding the payload we passed to `interrupt()`:

```python
from langgraph.types import Command

result = app.invoke(initial_state, config)       # config carries thread_id

while "__interrupt__" in result:
    payload = result["__interrupt__"][0].value   # what the node surfaced
    print(payload["flight_results"])
    print(payload["hotel_results"])

    answer = input("> ")                         # human types here
    result = app.invoke(Command(resume=answer), config)   # resume the SAME thread
```

State extension: `TravelState` gained one field — `approved: bool`.

---

## 6. Running it

```bash
source langgraph_env3/bin/activate

# 1. Small standalone demo (InMemorySaver, 3-node graph, heavily commented)
python src/mcp_hitl_demo.py "5 day trip to Tokyo"

# 2. Full app with interactive review (PostgresSaver)
python main.py

# 3. Web UI (auto-approves the review step — see section 7)
streamlit run frontend.py
```

### Example CLI session

```text
Enter travel request: plan a 3 day trip to Tokyo

========== REVIEW (graph paused) ==========
FLIGHTS:  ...
HOTELS:   ...
Approve these search results, or give feedback to search again.
> find cheaper hotels                <- feedback: loops back to search

========== REVIEW (graph paused) ==========
HOTELS:   ...budget hotels this time...
> approve                            <- continues to itinerary + final plan

FINAL RESPONSE:
...
```

---

## 7. What the frontend does (for now)

`frontend.py` has no review form yet, so it **auto-approves**: when the stream
ends with an `"__interrupt__"` chunk, it resumes with `Command(resume="approve")`
and keeps streaming. The pipeline shows a "🙋 Human Review" step so you can see
where the pause happened.

```python
while True:
    interrupted = False
    for chunk in app.stream(stream_input, config=config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            interrupted = True
            continue
        render_chunk(chunk)
    if not interrupted:
        break
    stream_input = Command(resume="approve")     # auto-approve in the web UI
```

Interactive review in the browser (approve / feedback buttons) is a planned
follow-up; use the CLI for real human-in-the-loop today.

---

## 8. Files involved

| File | Role |
|---|---|
| `src/mcp_hitl_demo.py` | Minimal standalone demo of both patterns — read this first |
| `mcp_server/travel_mcp.py` | The MCP server (unchanged — it already existed) |
| `main.py` | MCP client + `call_mcp()`, `human_review` node, conditional edges, CLI resume loop |
| `frontend.py` | "🙋 Human Review" pipeline step + auto-approve on interrupt |

New dependencies: `mcp`, `langchain-mcp-adapters`.

---

## 9. Key takeaways

| Concept | One-liner |
|---|---|
| **MCP server** | Tools live in a separate process, spoken to over a protocol |
| **`MultiServerMCPClient`** | Launches the server and turns MCP tools into LangChain tools |
| **`asyncio.run(...)`** | Bridges async MCP calls into the sync graph |
| **`interrupt(payload)`** | Pauses the graph inside a node; payload goes to the human |
| **`Command(resume=answer)`** | Resumes the paused thread; the node re-runs with the answer |
| **Checkpointer** | Mandatory for HITL — it is where the paused state lives |
| **`"__interrupt__"`** | The key in results/stream chunks that signals "graph is paused" |

In simple words:

> The agents now *ask* a separate tool server for data instead of owning the
> tool code, and the graph *asks the human* "is this good?" before spending
> LLM calls on an itinerary built from bad data.
