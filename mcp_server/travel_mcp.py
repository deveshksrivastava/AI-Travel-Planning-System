"""
Travel Planner MCP Server
=========================

Exposes this project's travel tools over the Model Context Protocol (MCP) so any
MCP client (Claude Desktop, Claude Code, etc.) can search flights and hotels.

Run (stdio transport):
    pip install "mcp[cli]"
    python mcp_server/travel_mcp.py

Requires the same .env as the main app (AVIATIONSTACK_API_KEY, TAVILY_API_KEY).
"""

import os
import sys

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load the project's .env (one directory up from this file).
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

mcp = FastMCP("travel-planner")

AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")


@mcp.tool()
def search_flights(departure_iata: str = "", arrival_iata: str = "", limit: int = 5) -> str:
    """Search live flights via AviationStack.

    Args:
        departure_iata: Optional 3-letter departure airport IATA code (e.g. "DEL").
        arrival_iata: Optional 3-letter arrival airport IATA code (e.g. "NRT").
        limit: Max number of flights to return (1-20).
    """
    if not AVIATIONSTACK_API_KEY:
        return "Error: AVIATIONSTACK_API_KEY is not set."

    params = {"access_key": AVIATIONSTACK_API_KEY, "limit": max(1, min(limit, 20))}
    if departure_iata:
        params["dep_iata"] = departure_iata.upper()
    if arrival_iata:
        params["arr_iata"] = arrival_iata.upper()

    try:
        response = requests.get(
            "http://api.aviationstack.com/v1/flights", params=params, timeout=15
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return f"Error calling AviationStack: {e}"
    except ValueError:
        return "Error: AviationStack returned an invalid response."

    if "error" in data:
        return f"AviationStack error: {data['error'].get('message', data['error'])}"

    flights = []
    for flight in data.get("data", [])[:limit]:
        airline = flight.get("airline", {}).get("name", "Unknown")
        departure = flight.get("departure", {}).get("airport", "Unknown")
        arrival = flight.get("arrival", {}).get("airport", "Unknown")
        status = flight.get("flight_status", "Unknown")
        flights.append(
            f"Airline: {airline}\nDeparture: {departure}\nArrival: {arrival}\nStatus: {status}"
        )

    return "\n\n".join(flights) if flights else "No flights found for the given criteria."


@mcp.tool()
def search_hotels(query: str, max_results: int = 5) -> str:
    """Search hotels (and related web results) via Tavily.

    Args:
        query: What to search for, e.g. "best hotels in Tokyo under $150".
        max_results: Max number of results to return (1-10).
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY is not set."

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max(1, min(max_results, 10)))
    except Exception as e:  # noqa: BLE001 - surface any client/network error to the caller
        return f"Error calling Tavily: {e}"

    results = []
    for i, r in enumerate(response.get("results", []), 1):
        title = r.get("title", "Unknown")
        url = r.get("url", "")
        snippet = r.get("content", "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."
        results.append(f"{i}. {title}\n   {url}\n   {snippet}")

    return "\n\n".join(results) if results else "No hotel results found."


@mcp.tool()
def plan_trip(destination: str, days: int = 5, budget: str = "") -> str:
    """Build a lightweight trip brief by combining hotel search results.

    This is a stateless convenience tool. For the full multi-agent itinerary,
    use the main LangGraph app (`python main.py`), which also persists memory.

    Args:
        destination: City or country to plan for.
        days: Trip length in days.
        budget: Optional budget hint, e.g. "under $2000".
    """
    budget_part = f" {budget}" if budget else ""
    hotels = search_hotels(f"best hotels and sightseeing in {destination}{budget_part}")
    return (
        f"Trip brief for {destination} ({days} days){budget_part}:\n\n"
        f"Suggested stays & highlights:\n{hotels}\n\n"
        f"Tip: run the full agent pipeline (main.py) for a complete itinerary."
    )


if __name__ == "__main__":
    # Default transport is stdio, which is what MCP clients launch.
    try:
        mcp.run()
    except KeyboardInterrupt:
        sys.exit(0)
