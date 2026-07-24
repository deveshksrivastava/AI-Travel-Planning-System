"""
Small demo: MCP tools + Human-in-the-Loop in a LangGraph pipeline
=================================================================

Two concepts in ~120 lines:

1. MCP   - instead of importing tool functions directly, we connect to the
           project's MCP server (mcp_server/travel_mcp.py). The server runs
           as a SEPARATE PROCESS and we talk to it over the MCP protocol
           (stdio). `langchain-mcp-adapters` converts each MCP tool into a
           normal LangChain tool we can call from agents.

2. HITL  - the graph PAUSES mid-run using `interrupt()`. A human reads the
           search results and either types "approve" (continue to summary)
           or types feedback (loop back and search again with refinement).

Graph:

    START -> search_agent -> human_review -> summary_agent -> END
                  ^               |
                  |   feedback    |  "approve"
                  +---------------+

Run:
    source langgraph_env3/bin/activate
    python src/mcp_hitl_demo.py "5 day trip to Tokyo"
"""

import asyncio
import os
import sys
from typing import TypedDict

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

load_dotenv()  # GROQ_API_KEY (LLM) + keys used by the MCP server

# ---------------------------------------------------------------------------
# 1. CONNECT TO THE MCP SERVER
# ---------------------------------------------------------------------------
# The client is told HOW to launch the server (command + args). Every tool
# call spawns the server over stdio, sends an MCP request, and reads the
# MCP response. No direct Python import of the tool code happens here.

SERVER_PATH = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "travel_mcp.py")

mcp_client = MultiServerMCPClient(
    {
        "travel": {
            "command": sys.executable,      # this venv's python
            "args": [SERVER_PATH],
            "transport": "stdio",
        }
    }
)

# MCP is async; the graph is sync. asyncio.run() bridges the two.
mcp_tools = {t.name: t for t in asyncio.run(mcp_client.get_tools())}
print(f"Connected to MCP server. Tools discovered: {list(mcp_tools)}\n")


def call_mcp(tool_name: str, args: dict) -> str:
    """Call one MCP tool synchronously and return plain text.

    MCP responses are a LIST of content blocks (text, images, ...), so we
    join the text parts into one string for easy use in prompts.
    """
    result = asyncio.run(mcp_tools[tool_name].ainvoke(args))
    if isinstance(result, list):
        result = "\n".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in result
        )
    return result


# ---------------------------------------------------------------------------
# 2. STATE
# ---------------------------------------------------------------------------
class DemoState(TypedDict):
    user_query: str
    flight_results: str
    hotel_results: str
    summary: str
    approved: bool


# ---------------------------------------------------------------------------
# 3. AGENTS
# ---------------------------------------------------------------------------
def search_agent(state: DemoState):
    """Fetch flights + hotels THROUGH the MCP server (not direct imports)."""
    print(f"  [search_agent] searching via MCP for: {state['user_query']!r}")

    flights = call_mcp("search_flights", {"limit": 3})
    hotels = call_mcp("search_hotels", {"query": f"best hotels for {state['user_query']}",
                                        "max_results": 3})

    return {"flight_results": flights, "hotel_results": hotels}


def human_review(state: DemoState):
    """PAUSE the graph and wait for a human decision.

    interrupt() stops execution here and saves everything to the
    checkpointer. The value we pass is shown to the human. When the caller
    resumes with Command(resume=<answer>), this node RE-RUNS and
    interrupt() returns that answer.
    """
    answer = interrupt(
        {
            "question": "Type 'approve' to continue, or feedback to search again.",
            "flight_results": state["flight_results"],
            "hotel_results": state["hotel_results"],
        }
    )

    if answer.strip().lower() == "approve":
        return {"approved": True}

    # Feedback -> refine the query and signal the router to search again.
    return {
        "approved": False,
        "user_query": f"{state['user_query']} (user feedback: {answer})",
    }


def route_after_review(state: DemoState) -> str:
    """Conditional edge: approve -> summary, feedback -> search again."""
    return "summary_agent" if state["approved"] else "search_agent"


def summary_agent(state: DemoState):
    """LLM writes a short plan from the approved results."""
    print("  [summary_agent] writing summary with Groq LLM...")
    llm = ChatGroq(model="llama-3.3-70b-versatile")
    response = llm.invoke(
        f"Write a short travel plan (max 150 words).\n"
        f"Request: {state['user_query']}\n"
        f"Flights:\n{state['flight_results']}\n"
        f"Hotels:\n{state['hotel_results']}"
    )
    return {"summary": response.content}


# ---------------------------------------------------------------------------
# 4. BUILD THE GRAPH
# ---------------------------------------------------------------------------
builder = StateGraph(DemoState)
builder.add_node("search_agent", search_agent)
builder.add_node("human_review", human_review)
builder.add_node("summary_agent", summary_agent)

builder.add_edge(START, "search_agent")
builder.add_edge("search_agent", "human_review")
builder.add_conditional_edges("human_review", route_after_review,
                              ["search_agent", "summary_agent"])
builder.add_edge("summary_agent", END)

# interrupt() REQUIRES a checkpointer (state must survive the pause).
app = builder.compile(checkpointer=InMemorySaver())


# ---------------------------------------------------------------------------
# 5. RUN: invoke -> pause -> human answers -> resume
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or input("Travel request: ")
    config = {"configurable": {"thread_id": "demo"}}

    result = app.invoke({"user_query": query, "approved": False}, config)

    # While the graph is paused, the result contains "__interrupt__".
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print("\n================ GRAPH PAUSED (human-in-the-loop) ================")
        print("FLIGHTS:\n" + payload["flight_results"][:500])
        print("\nHOTELS:\n" + payload["hotel_results"][:500])
        print("\n" + payload["question"])

        answer = input("> ")
        # Command(resume=...) hands the answer back to interrupt() above.
        result = app.invoke(Command(resume=answer), config)

    print("\n================ FINAL SUMMARY ================\n")
    print(result["summary"])
