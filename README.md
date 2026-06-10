# AI Travel Planning System using LangGraph

This project is a Real-World Multi-Agent AI System built using LangGraph.

The system uses 4 AI agents that work together to plan a complete trip automatically.

## Features

- ✈️ Flight Search Agent
- 🏨 Hotel Search Agent
- 🗓️ Itinerary Planning Agent
- 🤖 Final Response Agent
- 🧠 Memory using PostgreSQL
- 🌐 Real-time API Integration
- 💻 Streamlit Web Interface

---

# Tech Stack

- LangGraph
- LangChain
- Groq
- Llama 3.3 70B
- PostgreSQL
- Streamlit
- Tavily API
- AviationStack API

---

# Architecture Diagram

The system is a **multi-agent pipeline** orchestrated by LangGraph. A shared
`TravelState` object is passed between four agents, each enriching it before
the next runs. External APIs supply real-time data, Groq (Llama 3.3 70B)
powers the reasoning agents, and a PostgreSQL checkpointer persists state.

```mermaid
flowchart TB
    subgraph UI["🖥️ User Interfaces"]
        CLI["CLI<br/>(main.py)"]
        WEB["Streamlit Web App<br/>(frontend.py)"]
    end

    subgraph CORE["⚙️ LangGraph Orchestration"]
        direction TB
        APP["Compiled Graph (app)"]
        STATE["Shared TravelState<br/>messages · user_query · flight_results<br/>hotel_results · itinerary · llm_calls"]
        APP -.reads / writes.-> STATE
    end

    subgraph AGENTS["🤖 Agents"]
        direction LR
        FA["Flight Agent"]
        HA["Hotel Agent"]
        IA["Itinerary Agent"]
        FRA["Final Response Agent"]
    end

    subgraph EXT["🌐 External Services"]
        AV["AviationStack API<br/>(flights)"]
        TV["Tavily Search API<br/>(hotels)"]
        GROQ["Groq · Llama 3.3 70B<br/>(LLM reasoning)"]
    end

    subgraph MEM["🧠 Memory"]
        PG[("PostgreSQL<br/>PostgresSaver checkpointer")]
    end

    CLI --> APP
    WEB --> APP
    APP --> AGENTS

    FA --> AV
    HA --> TV
    IA --> GROQ
    FRA --> GROQ

    APP <--> PG
```

---

# Flow Diagram

Execution is **sequential**: each agent runs in a fixed order, writing its
results into the shared state. After all four agents complete, the state is
checkpointed to PostgreSQL and the final response is returned.

```mermaid
flowchart LR
    START([START]) --> FA["✈️ Flight Agent<br/>search_flights()"]
    FA --> HA["🏨 Hotel Agent<br/>tavily_search()"]
    HA --> IA["🗓️ Itinerary Agent<br/>llm.invoke()"]
    IA --> FRA["🤖 Final Response Agent<br/>llm.invoke()"]
    FRA --> END([END])

    FA -. writes .-> S1[/"flight_results"/]
    HA -. writes .-> S2[/"hotel_results"/]
    IA -. writes .-> S3[/"itinerary"/]
    FRA -. writes .-> S4[/"final messages"/]
```

### Step-by-step

```mermaid
sequenceDiagram
    actor User
    participant App as LangGraph (app)
    participant Flight as Flight Agent
    participant Hotel as Hotel Agent
    participant Itin as Itinerary Agent
    participant Final as Final Agent
    participant DB as PostgreSQL

    User->>App: Travel request (user_query)
    App->>Flight: invoke with TravelState
    Flight->>Flight: AviationStack → flight_results
    Flight-->>App: updated state
    App->>Hotel: invoke
    Hotel->>Hotel: Tavily → hotel_results
    Hotel-->>App: updated state
    App->>Itin: invoke
    Itin->>Itin: Groq LLM → itinerary
    Itin-->>App: updated state
    App->>Final: invoke
    Final->>Final: Groq LLM → final answer
    Final-->>App: updated state
    App->>DB: checkpoint state (thread_id)
    App-->>User: Final travel plan
```

---

# Step 1: Create Python Environment

Open the terminal inside the project folder and run:

		python -m venv langgraph_env3


Now activate the environment:

#### Windows

		langgraph_env3\Scripts\activate


#### YouTube Tuturial (Hindi) - https://youtu.be/ctHby5vhDqg

---

# Step 2: Install Dependencies

Run the following command:

		pip install langgraph langchain langchain-openai langchain-groq langchain-community langchain-tavily psycopg[binary] psycopg_pool python-dotenv tavily-python requests streamlit

		pip install -U "psycopg[binary,pool]"  langgraph-checkpoint-postgres

---

# Step 3: Install PostgreSQL

Download and install PostgreSQL: https://www.postgresql.org/download/

⚠️ Important:
While installing PostgreSQL, remember:
- PostgreSQL Password
- Port Number

You will need them later while creating the database connection string.

---

# Step 4: Create Database

Open PostgreSQL and run:

CREATE DATABASE langgraph_memory_demo;


---

# Step 5: Setup `.env` File

Create a `.env` file inside the project folder.

Add the following keys:

GROQ_API_KEY=your_groq_api_key

TAVILY_API_KEY=your_tavily_api_key

AVIATIONSTACK_API_KEY=your_aviationstack_api_key

DATABASE_URL=postgresql://postgres:postgres@localhost:5433/langgraph_memory_demo


Create Key from below
  - Groq → https://console.groq.com
  - Tavily → https://tavily.com
  - AviationStack → https://aviationstack.com


---

# Step 6: Get API Keys

## Get Groq API Key

https://console.groq.com

---

## Get Tavily API Key

https://tavily.com
  
---

## Get AviationStack API Key

https://aviationstack.com

---

# Step 7: Run the Application

#### Run Multi-Agent System in Terminal

		python main.py


This will test the multi-agent system through the terminal.

---

#### Run Streamlit Web App


		streamlit run frontend.py


This will launch the Multi-Agent AI web application.

---

#### Example Prompt

Plan a complete 7 days Japan trip including flights, hotels and sightseeing under 2 lakhs.


---

# Project Workflow

1. Flight Agent searches flights
2. Hotel Agent searches hotels
3. Itinerary Agent creates travel plan
4. Final Agent combines everything together
5. PostgreSQL stores conversation memory

