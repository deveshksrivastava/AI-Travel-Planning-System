# Learn AutoGen: Agents, Teams, Termination, and Messages

> This is a companion to [`learn-graph.md`](./learn-graph.md). It rebuilds the
> **same task-management example** (add task / complete task / summarize) using
> **AutoGen** (v0.4+ `autogen-agentchat`) instead of LangGraph, so you can compare
> the two frameworks side by side.

## 1. What is AutoGen?

AutoGen is a Microsoft framework for building **conversational multi-agent
applications**. Agents talk to each other (and optionally to humans) by passing
**messages**, and a **team** decides whose turn it is to speak next.

Instead of a graph of nodes and edges, you have a **conversation between
agents**:

```text
User message  →  Agent A speaks  →  Agent B speaks  →  ... →  Termination
```

This makes AutoGen useful for **chat-style agents**, **tool-using assistants**,
**agent debates**, and **human-in-the-loop** workflows.

> ⚠️ **Version note:** AutoGen was rewritten in v0.4. This guide uses the modern
> `autogen-agentchat` API (`AssistantAgent`, teams, `Console`). The old
> `autogen` v0.2 `ConversableAgent` / `initiate_chat` style is different.
> Install with: `pip install -U "autogen-agentchat" "autogen-ext[openai]"`

---

## 2. Core Concepts

| Concept | Simple Meaning | Example | LangGraph Equivalent |
|---|---|---|---|
| **AssistantAgent** | An LLM agent that can reply and use tools | Intent classifier, task handler | A node + LLM |
| **Model Client** | The LLM connection | `OpenAIChatCompletionClient(...)` | The `llm` object |
| **Tool** | A Python function an agent can call | `add_task()`, `complete_task()` | A tool function |
| **Team** | A group of agents that take turns | `RoundRobinGroupChat`, `SelectorGroupChat` | The graph |
| **Termination** | Condition that stops the chat | `TextMentionTermination("DONE")` | Reaching `END` |
| **run() / run_stream()** | Start the conversation | `team.run(task=...)` | `graph.invoke(...)` |

> **Key mental shift:** LangGraph passes *state* between functions. AutoGen
> passes *messages* between agents. The "router" in AutoGen is a **team's
> speaker-selection policy** (round-robin, or an LLM-driven selector).

---

## 3. Simple Flow Diagram

```text
run(user_input)
  |
  v
SelectorGroupChat decides who speaks
  |
  |-- intent looks like "add"      ---> Add Agent      -> uses add_task()      -> DONE
  |
  |-- intent looks like "complete" ---> Complete Agent -> uses complete_task() -> DONE
  |
  |-- otherwise                    ---> Summary Agent  -> uses summarize()     -> DONE
```

In AutoGen the "conditional edge" is the **selector** that reads the
conversation and picks the next agent to speak.

---

## 4. AutoGen Example Code

```python
import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient


# 1. Define the model client (the LLM connection)
model_client = OpenAIChatCompletionClient(model="gpt-4o")
# api_key is read from the OPENAI_API_KEY environment variable if not passed.


# 2. Define simple tools — the actual task-management actions
def add_task(name: str) -> str:
    """Add a task to the to-do list."""
    return "Task added successfully."

def complete_task(name: str) -> str:
    """Mark a task as completed."""
    return "Task marked as completed."

def summarize_tasks() -> str:
    """Summarize all current tasks."""
    return "Here is the summary of your tasks."


# 3. Define agents — each specialises in one branch.
#    Each ends its reply with "DONE" so the team knows to stop.
add_agent = AssistantAgent(
    name="add_agent",
    model_client=model_client,
    tools=[add_task],
    system_message=(
        "You handle requests to ADD a task. If the user wants to add something, "
        "call add_task and then reply with the result followed by 'DONE'. "
        "If the request is not about adding, stay silent."
    ),
)

complete_agent = AssistantAgent(
    name="complete_agent",
    model_client=model_client,
    tools=[complete_task],
    system_message=(
        "You handle requests to COMPLETE or mark a task done. If so, call "
        "complete_task and reply with the result followed by 'DONE'. "
        "Otherwise stay silent."
    ),
)

summary_agent = AssistantAgent(
    name="summary_agent",
    model_client=model_client,
    tools=[summarize_tasks],
    system_message=(
        "You handle every other request by summarizing tasks. Call "
        "summarize_tasks and reply with the result followed by 'DONE'."
    ),
)


# 4. Build the team. The SelectorGroupChat reads the conversation and the
#    agents' descriptions to pick who should respond next (the "router").
termination = TextMentionTermination("DONE")

team = SelectorGroupChat(
    [add_agent, complete_agent, summary_agent],
    model_client=model_client,
    termination_condition=termination,
)


# 5. Run the team on a user request
async def main() -> None:
    await Console(team.run_stream(task="add buy milk"))
    await model_client.close()


asyncio.run(main())
```

> **Note:** Like CrewAI, AutoGen agents are LLM-driven. The routing decision is
> made by the model (the selector), not by hand-written Python `if` statements
> as in the LangGraph example.

---

## 5. Expected Output

If the task is:

```python
team.run_stream(task="add buy milk")
```

The conversation flow is:

```text
user: add buy milk
  -> selector picks add_agent
  -> add_agent calls add_task("buy milk")
  -> add_agent: "Task added successfully. DONE"
  -> termination condition met (text "DONE") -> stop
```

The streamed result ends with something like:

```text
Task added successfully. DONE
```

`run()` returns a `TaskResult` object — inspect `result.messages` to see the
full back-and-forth conversation.

---

## 6. Alternative Style: RoundRobinGroupChat (No Selector)

If you don't need intelligent routing, the simplest team just lets agents speak
**in a fixed order** until termination — the AutoGen equivalent of a plain
LangGraph edge chain:

```python
from autogen_agentchat.teams import RoundRobinGroupChat

team = RoundRobinGroupChat(
    [add_agent, complete_agent, summary_agent],
    termination_condition=TextMentionTermination("DONE"),
)

await Console(team.run_stream(task="add buy milk"))
```

`RoundRobinGroupChat` = fixed turn order (like `add_edge(a, b)`).
`SelectorGroupChat` = dynamic, model-chosen turns (like a conditional edge).

For a single agent with no team at all (the smallest possible setup):

```python
agent = AssistantAgent("assistant", model_client=model_client, tools=[add_task])
print(await agent.run(task="add buy milk"))
```

---

## 7. Key Takeaway

| AutoGen Term | Meaning |
|---|---|
| **AssistantAgent** | An LLM agent that replies and can call tools |
| **Model Client** | The connection to the underlying LLM |
| **Tool** | A Python function the agent may call |
| **Team** | A group of agents that take turns (RoundRobin / Selector) |
| **Termination** | The rule that ends the conversation |

In simple words:

> AutoGen lets you build AI workflows as a **conversation between agents**, where
> each agent is a specialist, messages are the shared memory, and a team decides
> who speaks next until a termination condition is reached.

---

## 8. Why AutoGen is Useful

Use AutoGen when:

- Your workflow is naturally a **conversation** between agents
- You want **human-in-the-loop** steps (a `UserProxyAgent` can join the chat)
- You want agents to **debate, critique, or collaborate** via messages
- You need flexible, model-driven turn-taking rather than fixed routes

LangGraph gives you explicit control over **state and graph edges**. AutoGen
gives you a **message-passing, conversational** abstraction. For deterministic
pipelines you control, LangGraph is clearer; for chat-style, collaborative, or
human-in-the-loop agents, AutoGen fits naturally.
