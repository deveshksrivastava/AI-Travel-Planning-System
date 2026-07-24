'''
# pip install langgraph langchain langchain-openai langchain-groq langchain-community langchain-tavily psycopg[binary] psycopg_pool python-dotenv tavily-python pip install requests streamlit

# install PostgresSql and create database
CREATE DATABASE langgraph_memory;  ( or open pgadmin4 and create database there )
'''
# LangGraph Multi-Agent Travel Booking System with Long-Term Memory

# main.py

import os
import sys
import atexit
import asyncio
from typing import TypedDict, Annotated
import operator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import interrupt, Command
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)

from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# MCP client: tools are no longer imported directly — they are served by
# mcp_server/travel_mcp.py (a separate process) and called over the MCP
# protocol (stdio). See src/mcp_hitl_demo.py for a minimal walkthrough.
_MCP_SERVER = os.path.join(os.path.dirname(__file__), "mcp_server", "travel_mcp.py")

mcp_client = MultiServerMCPClient(
    {
        "travel": {
            "command": sys.executable,
            "args": [_MCP_SERVER],
            "transport": "stdio",
        }
    }
)

# MCP is async; this graph is sync — asyncio.run() bridges the two.
mcp_tools = {t.name: t for t in asyncio.run(mcp_client.get_tools())}


def call_mcp(tool_name: str, args: dict) -> str:
    """Call one MCP tool synchronously and return plain text.

    MCP responses are a list of content blocks; join the text parts.
    """
    result = asyncio.run(mcp_tools[tool_name].ainvoke(args))
    if isinstance(result, list):
        result = "\n".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in result
        )
    return result

# LLM
llm = ChatGroq(
    model="llama-3.3-70b-versatile"
)

# State
class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int
    approved: bool

# Flight Agent
def flight_agent(state: TravelState):
    flight_data = call_mcp("search_flights", {"limit": 5})
    return {
        "flight_results": flight_data,
        "messages": [
            AIMessage(content=f"Flight results fetched")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# Hotel Agent
def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    hotel_results = call_mcp("search_hotels", {"query": query, "max_results": 5})

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content="Hotel information fetched")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# Human Review (human-in-the-loop)
def human_review(state: TravelState):
    """Pause the graph after search and wait for a human decision.

    interrupt() suspends the run and persists state in the checkpointer.
    Resuming with Command(resume=<answer>) re-runs this node, and
    interrupt() returns the human's answer.
    """
    answer = interrupt(
        {
            "question": "Approve these search results, or give feedback to search again.",
            "flight_results": state["flight_results"],
            "hotel_results": state["hotel_results"],
        }
    )

    if str(answer).strip().lower() == "approve":
        return {
            "approved": True,
            "messages": [HumanMessage(content="Search results approved")],
        }

    # Feedback: refine the query and route back to search.
    return {
        "approved": False,
        "user_query": f"{state['user_query']} (user feedback: {answer})",
        "messages": [HumanMessage(content=f"Feedback: {answer}")],
    }


def route_after_review(state: TravelState) -> str:
    """approve -> itinerary_agent, feedback -> search again."""
    return "itinerary_agent" if state["approved"] else "flight_agent"

# Itinerary Agent
def itinerary_agent(state: TravelState):

    prompt = f"""
    Create a travel itinerary.
    User Query:
    {state['user_query']}

    Flight Results:
    {state['flight_results']}

    Hotel Results:
    {state['hotel_results']}
    """

    response = llm.invoke([
        SystemMessage(
            content="You are an expert travel planner"
        ),
        HumanMessage(content=prompt)
    ])

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

# Final Response Agent
def final_agent(state: TravelState):

    final_prompt = f"""
    Generate final travel response.

    Flights:
    {state['flight_results']}

    Hotels:
    {state['hotel_results']}

    Itinerary:
    {state['itinerary']}
    """

    response = llm.invoke([
        HumanMessage(content=final_prompt)
    ])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("human_review", human_review)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "human_review")
graph.add_conditional_edges("human_review", route_after_review,
                            ["flight_agent", "itinerary_agent"])
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)

# START
#   |
# flight_agent
#   |
# hotel_agent
#   |
# human_review  <-- pauses (interrupt); approve -> continue,
#   |  ^            feedback -> back to flight_agent
# itinerary_agent
#   |
# final_agent
#   |
# END

# Connection pool shared by both the CLI and the long-running Streamlit app.
# A pool (rather than a single global connection) survives idle drops and
# Postgres restarts: check_connection validates — and transparently replaces —
# dead connections before they are handed out, so a long-lived process no
# longer fails with "server closed the connection unexpectedly".
# autocommit is required by PostgresSaver.setup() (CREATE INDEX CONCURRENTLY
# cannot run inside a transaction block).
_pool = ConnectionPool(
    conninfo=DATABASE_URL,
    max_size=20,
    check=ConnectionPool.check_connection,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    },
    open=True,
)
checkpointer = PostgresSaver(_pool)
checkpointer.setup()

# Close the pool's worker threads cleanly on process exit (avoids noisy
# "couldn't stop thread" warnings when the CLI finishes a run).
atexit.register(_pool.close)

app = graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    config = {
        "configurable": {
            "thread_id": "user_aarohi"
        }
    }

    user_input = input("Enter travel request: ")

    result = app.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0,
            "approved": False
        },
        config=config
    )

    # Human-in-the-loop: while paused, show the search results and ask.
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print("\n========== REVIEW (graph paused) ==========")
        print("\nFLIGHTS:\n" + payload["flight_results"])
        print("\nHOTELS:\n" + payload["hotel_results"])
        print("\n" + payload["question"])
        answer = input("> ")
        result = app.invoke(Command(resume=answer), config=config)

    print("\nFINAL RESPONSE:\n")

    for msg in result["messages"]:
        print(msg.content)
