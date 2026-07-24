from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from langchain_core.messages import AnyMessage
import operator


# ==================================================
# STATE
# ==================================================

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]

    user_query: str

    flight_results: str
    hotel_results: str

    itinerary: str

    retry_count: int
    human_approved: bool

    llm_calls: int


# ==================================================
# COORDINATOR
# ==================================================

def coordinator(state: TravelState):

    print("Coordinator Agent")

    return {}


# ==================================================
# FLIGHT AGENT
# ==================================================

def flight_agent(state: TravelState):

    print("Flight Agent")

    try:

        flight = "London -> Paris | BA | £120"

        return {
            "flight_results": flight,
            "llm_calls": state["llm_calls"] + 1
        }

    except Exception:

        return {
            "retry_count":
                state["retry_count"] + 1
        }


# ==================================================
# RETRY ROUTER
# ==================================================

MAX_RETRY = 3

def flight_router(state: TravelState):

    if state["flight_results"]:
        return "success"

    if state["retry_count"] >= MAX_RETRY:
        return "human"

    return "retry"


# ==================================================
# HOTEL AGENT
# ==================================================

def hotel_agent(state: TravelState):

    print("Hotel Agent")

    return {
        "hotel_results":
            "Hilton Paris | £150/night",

        "llm_calls":
            state["llm_calls"] + 1
    }


# ==================================================
# HUMAN REVIEW
# ==================================================

def human_review(state: TravelState):

    approval = interrupt(
        {
            "question":
                "Approve Travel Plan?",

            "flight":
                state["flight_results"],

            "hotel":
                state["hotel_results"]
        }
    )

    return {
        "human_approved": approval
    }


# ==================================================
# APPROVAL ROUTER
# ==================================================

def approval_router(state: TravelState):

    if state["human_approved"]:
        return "approved"

    return "rejected"


# ==================================================
# ITINERARY AGENT
# ==================================================

def itinerary_agent(state: TravelState):

    itinerary = f"""
    TRAVEL PLAN

    User:
    {state['user_query']}

    Flight:
    {state['flight_results']}

    Hotel:
    {state['hotel_results']}

    Day 1: Arrival
    Day 2: Eiffel Tower
    Day 3: Louvre
    Day 4: Cruise
    Day 5: Return
    """

    return {
        "itinerary": itinerary,
        "llm_calls": state["llm_calls"] + 1
    }


# ==================================================
# GRAPH
# ==================================================

builder = StateGraph(TravelState)

builder.add_node(
    "coordinator",
    coordinator
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
    "human_review",
    human_review
)

builder.add_node(
    "itinerary_agent",
    itinerary_agent
)


# ==================================================
# FLOW
# ==================================================

builder.add_edge(
    START,
    "coordinator"
)

builder.add_edge(
    "coordinator",
    "flight_agent"
)

builder.add_conditional_edges(
    "flight_agent",
    flight_router,
    {
        "success":
            "hotel_agent",

        "retry":
            "flight_agent",

        "human":
            "human_review"
    }
)

builder.add_edge(
    "hotel_agent",
    "human_review"
)

builder.add_conditional_edges(
    "human_review",
    approval_router,
    {
        "approved":
            "itinerary_agent",

        "rejected":
            "flight_agent"
    }
)

builder.add_edge(
    "itinerary_agent",
    END
)


# ==================================================
# CHECKPOINTING
# ==================================================

memory = MemorySaver()

graph = builder.compile(
    checkpointer=memory
)


# ==================================================
# RUN
# ==================================================

config = {
    "configurable": {
        "thread_id": "travel-001"
    }
}

result = graph.invoke(
    {
        "messages": [],
        "user_query":
            "Plan 5 day Paris trip",

        "flight_results": "",
        "hotel_results": "",

        "itinerary": "",

        "retry_count": 0,

        "human_approved": False,

        "llm_calls": 0
    },
    config=config
)

print(result)


# Production Architecture
# User
#   |
#   v
# Coordinator
#   |
#   +--> Flight Agent
#   |        |
#   |        +--> Retry?
#   |
#   +--> Hotel Agent
#   |        |
#   |        +--> Retry?
#   |
#   +--> Human Approval
#   |        |
#   |        +--> Approve
#   |        +--> Reject
#   |
#   +--> Itinerary Agent
#   |
#  END

# Complete Enterprise Flow Production Architecture
# User
#   |
#   v
# Coordinator
#   |
#   +--> Flight Agent
#   |        |
#   |        +--> Retry?
#   |
#   +--> Hotel Agent
#   |        |
#   |        +--> Retry?
#   |
#   +--> Human Approval
#   |        |
#   |        +--> Approve
#   |        +--> Reject
#   |
#   +--> Itinerary Agent
#   |
#  END


# ┌───────────────────────────────┐
# │            START              │
# └───────────────┬───────────────┘
#                 │
#                 ▼
# ┌───────────────────────────────┐
# │      Coordinator Agent        │
# │  - Read user request          │
# │  - Create execution plan      │
# └───────────────┬───────────────┘
#                 │
#                 ▼
# ┌───────────────────────────────┐
# │        Flight Agent           │
# │  - Search flights             │
# │  - Call Flight API            │
# └───────────────┬───────────────┘
#                 │
#                 ▼
#       ┌─────────────────┐
#       │ Flight Success? │
#       └───────┬─────────┘
#               │
#       ┌───────┴─────────┐
#       │                 │
#       ▼                 ▼
#  SUCCESS            FAILED
#       │                 │
#       │          ┌──────────────┐
#       │          │ Retry Count? │
#       │          └──────┬───────┘
#       │                 │
#       │        ┌────────┴────────┐
#       │        │                 │
#       ▼        ▼                 ▼
# Hotel Agent  Retry <3      Human Review
#                                  │
#                                  ▼
#                          Manual Correction
#                                  │
#                                  ▼
#                             Hotel Agent


# ┌───────────────────────────────┐
# │         Hotel Agent           │
# │  - Search Hotels              │
# │  - Call Booking API           │
# └───────────────┬───────────────┘
#                 │
#                 ▼
#       ┌─────────────────┐
#       │ Hotel Success?  │
#       └───────┬─────────┘
#               │
#       ┌───────┴─────────┐
#       │                 │
#       ▼                 ▼
#  SUCCESS            FAILED
#       │                 │
#       │          Retry Logic
#       │                 │
#       ▼                 ▼
# ┌───────────────────────────────┐
# │      Human Approval Node      │
# │                               │
# │ Flight: London→Paris £120     │
# │ Hotel : Hilton £150/night     │
# │                               │
# │ Approve? Yes / No             │
# └───────────────┬───────────────┘
#                 │
#        ┌────────┴────────┐
#        │                 │
#        ▼                 ▼
#  APPROVED           REJECTED
#        │                 │
#        │                 │
#        │         Back To Flight
#        │         or Hotel Agent
#        │
#        ▼
# ┌───────────────────────────────┐
# │      Itinerary Agent          │
# │                               │
# │ Build Final Travel Plan       │
# │ Combine All Results           │
# └───────────────┬───────────────┘
#                 │
#                 ▼
# ┌───────────────────────────────┐
# │             END               │
# └───────────────────────────────┘