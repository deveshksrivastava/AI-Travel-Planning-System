# Travel Planner MCP Server

Exposes this project's travel tools over the **Model Context Protocol (MCP)** so
any MCP client (Claude Desktop, Claude Code, IDE extensions) can call them.

## Tools

| Tool | Description |
|---|---|
| `search_flights(departure_iata, arrival_iata, limit)` | Live flight search via AviationStack |
| `search_hotels(query, max_results)` | Hotel/web search via Tavily |
| `plan_trip(destination, days, budget)` | Lightweight stateless trip brief |

## Install & Run

```bash
source ../langgraph_env3/bin/activate      # or your venv
pip install "mcp[cli]" requests tavily-python python-dotenv

python travel_mcp.py                        # runs over stdio
```

The server reads the project `.env` (one level up): it needs
`AVIATIONSTACK_API_KEY` and `TAVILY_API_KEY`.

## Connect from Claude Code

```bash
claude mcp add travel-planner -- python /absolute/path/to/mcp_server/travel_mcp.py
```

## Connect from Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "travel-planner": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_server/travel_mcp.py"]
    }
  }
}
```

Restart the client, then ask it to "search flights from DEL to NRT" or
"find hotels in Tokyo under $150" — it will call these tools.

## Notes

- Transport is **stdio** (the default MCP clients launch). For HTTP, change
  `mcp.run()` to `mcp.run(transport="streamable-http")`.
- These tools add timeouts and error handling that the in-app versions lack
  (see `PRODUCTION_READINESS.md`).
