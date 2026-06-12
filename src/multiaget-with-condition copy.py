# travel_multi_agent.py

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AnyMessage
import operator


# =====================================================
# STATE
# =====================================================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]

    user_query: str

    flight_results: str
    hotel_results: str

    itinerary: str

    llm_calls: int


# =====================================================
# COORDINATOR AGENT
# =====================================================

def coordinator_agent(state: TravelState):

    print("\n===== COORDINATOR =====")
    print(f"User Query: {state['user_query']}")

    return {}


# =====================================================
# FLIGHT AGENT
# =====================================================

def flight_agent(state: TravelState):

    print("\n===== FLIGHT AGENT =====")

    return {
        "flight_results":
            "London -> Paris | British Airways | £120",

        "llm_calls":
            state["llm_calls"] + 1
    }


# =====================================================
# HOTEL AGENT
# =====================================================

def hotel_agent(state: TravelState):

    print("\n===== HOTEL AGENT =====")

    return {
        "hotel_results":
            "Hilton Paris | £150/night",

        "llm_calls":
            state["llm_calls"] + 1
    }


# =====================================================
# ITINERARY AGENT
# =====================================================

def itinerary_agent(state: TravelState):

    print("\n===== ITINERARY AGENT =====")

    itinerary = f"""
=================================
FINAL TRAVEL PLAN
=================================

User Request:
{state['user_query']}

Flight:
{state['flight_results']}

Hotel:
{state['hotel_results']}

Suggested Duration:
5 Days

Day 1:
Arrival + Eiffel Tower

Day 2:
Louvre Museum

Day 3:
Seine River Cruise

Day 4:
Versailles

Day 5:
Shopping + Return

=================================
"""

    return {
        "itinerary": itinerary,
        "llm_calls": state["llm_calls"] + 1
    }


# =====================================================
# BUILD GRAPH
# =====================================================

builder = StateGraph(TravelState)

builder.add_node(
    "coordinator_agent",
    coordinator_agent
)

builder.add_node(
    "flight_agent",
    flight_agent
)

builder.add_node(
    "hotel_agent",
    hotel_agent
)

builder.add_node(
    "itinerary_agent",
    itinerary_agent
)


# =====================================================
# EDGES
# =====================================================

builder.add_edge(
    START,
    "coordinator_agent"
)

builder.add_edge(
    "coordinator_agent",
    "flight_agent"
)

builder.add_edge(
    "coordinator_agent",
    "hotel_agent"
)

builder.add_edge(
    "flight_agent",
    "itinerary_agent"
)

builder.add_edge(
    "hotel_agent",
    "itinerary_agent"
)

builder.add_edge(
    "itinerary_agent",
    END
)


# =====================================================
# COMPILE GRAPH
# =====================================================

graph = builder.compile()


# =====================================================
# RUN GRAPH
# =====================================================

if __name__ == "__main__":

    initial_state = {
        "messages": [],
        "user_query": "Plan a 5 day trip to Paris",

        "flight_results": "",
        "hotel_results": "",

        "itinerary": "",

        "llm_calls": 0
    }

    result = graph.invoke(initial_state)

    print(result["itinerary"])

    print(f"\nTotal LLM Calls: {result['llm_calls']}")


#     Flow
# START
#   |
#   v
# Coordinator Agent
#   |
#   +-------------------+
#   |                   |
#   v                   v
# Flight Agent     Hotel Agent
#   |                   |
#   +--------+----------+
#            |
#            v
#     Itinerary Agent
#            |
#            v
#           END