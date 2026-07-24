# Learn CrewAI: Agents, Tasks, Crews, and Process

> This is a companion to [`learn-graph.md`](./learn-graph.md). It rebuilds the
> **same task-management example** (add task / complete task / summarize) using
> **CrewAI** instead of LangGraph, so you can compare the two frameworks side by side.

## 1. What is CrewAI?

CrewAI is a framework used to build **role-based multi-agent systems**.

Instead of thinking in terms of a graph of nodes and edges, you think in terms
of a **team (crew) of agents**, where each agent has a *role*, a *goal*, and a
*backstory*. You give the crew a list of **tasks**, and a **process** decides
the order in which agents work:

```text
Crew  →  [ Agent 1, Agent 2, Agent 3 ]  →  works through Tasks  →  Final Output
```

This makes CrewAI useful for **collaborative agents**, **assistant teams**,
**research/writing pipelines**, and **autonomous workflows** where each agent
behaves like a specialist team member.

---

## 2. Core Concepts

| Concept | Simple Meaning | Example | LangGraph Equivalent |
|---|---|---|---|
| **Agent** | A specialist worker with a role | Intent classifier, task handler | (No direct equivalent — closest is a node + LLM) |
| **Task** | A unit of work assigned to an agent | "Decide the user's intent" | A node |
| **Crew** | The team of agents + tasks | The whole task manager | The compiled graph |
| **Process** | The order agents run in | `sequential`, `hierarchical` | Edges |
| **Conditional Task** | A task that only runs if a condition is met | Run "add task" only if intent is add | Conditional edge |
| **kickoff()** | Starts the crew running | `crew.kickoff(inputs=...)` | `graph.invoke(...)` |

> **Key mental shift:** LangGraph routes *data through functions*. CrewAI
> assigns *work to agents*. Both share state, but CrewAI's "state" flows as
> task **context** (the output of one task feeds into the next).

---

## 3. Simple Flow Diagram

```text
kickoff(user_input)
  |
  v
Intent Agent  ->  classify_task   (decides: add / complete / summarize)
  |
  |-- if intent == add_task ---------> Add Task  (Conditional Task) ----> Output
  |
  |-- if intent == complete_task ----> Complete Task (Conditional Task)-> Output
  |
  |-- otherwise ---------------------> Summarize Task (Conditional Task)-> Output
```

In CrewAI the "router" is not a separate edge function — it is an **agent that
classifies intent**, plus **conditional tasks** that decide whether to run based
on that classification.

---

## 4. CrewAI Example Code

```python
from crewai import Agent, Task, Crew, Process
from crewai.tasks.conditional_task import ConditionalTask
from crewai.tasks.task_output import TaskOutput


# 1. Define Agents (each has a role, goal, backstory)
classifier = Agent(
    role="Intent Classifier",
    goal="Read the user's request and decide if it is add / complete / summarize",
    backstory="You are precise at understanding what a user wants to do with their tasks.",
)

task_handler = Agent(
    role="Task Handler",
    goal="Perform the requested task-management action and reply to the user",
    backstory="You are a reliable assistant that manages a user's to-do list.",
)


# 2. Task: classify the user's intent
classify_task = Task(
    description=(
        "Read this user request: '{user_input}'. "
        "Respond with exactly one word: add_task, complete_task, or summarize."
    ),
    expected_output="One word: add_task, complete_task, or summarize",
    agent=classifier,
)


# 3. Conditional functions — decide whether each branch runs.
#    They inspect the previous task's output (the classified intent).
def is_add(output: TaskOutput) -> bool:
    return "add_task" in output.raw.lower()

def is_complete(output: TaskOutput) -> bool:
    return "complete_task" in output.raw.lower()

def is_summarize(output: TaskOutput) -> bool:
    text = output.raw.lower()
    return "add_task" not in text and "complete_task" not in text


# 4. Conditional Tasks — only the matching branch executes
add_task = ConditionalTask(
    description="Confirm to the user that the task was added successfully.",
    expected_output="Task added successfully.",
    agent=task_handler,
    condition=is_add,
)

complete_task = ConditionalTask(
    description="Confirm to the user that the task was marked as completed.",
    expected_output="Task marked as completed.",
    agent=task_handler,
    condition=is_complete,
)

summarize_task = ConditionalTask(
    description="Give the user a short summary of their tasks.",
    expected_output="Here is the summary of your tasks.",
    agent=task_handler,
    condition=is_summarize,
)


# 5. Build the Crew (the team + the ordered work)
crew = Crew(
    agents=[classifier, task_handler],
    tasks=[classify_task, add_task, complete_task, summarize_task],
    process=Process.sequential,
    verbose=True,
)


# 6. Run the Crew
result = crew.kickoff(inputs={"user_input": "add buy milk"})

print(result)
```

> **Note:** CrewAI agents are LLM-backed. You need an LLM configured (e.g. set
> `OPENAI_API_KEY`, or pass `llm=...` to each `Agent`). Unlike the pure-Python
> LangGraph example, the "logic" here is performed by the model following each
> agent's goal and task description.

---

## 5. Expected Output

If the input is:

```python
{"user_input": "add buy milk"}
```

The crew flow is:

```text
kickoff -> classify_task (intent = add_task) -> add_task (runs) -> Output
            (complete_task and summarize_task are skipped)
```

The final result will be similar to:

```text
Task added successfully.
```

`result` is a `CrewOutput` object — use `result.raw` for the text, or
`result.tasks_output` to inspect what each task produced.

---

## 6. Alternative Style: Sequential Process Without Conditions

If you don't need branching, the simplest CrewAI shape is a straight
**sequential pipeline**, where each task's output feeds the next via `context`:

```python
research = Task(description="Research the topic", expected_output="Notes", agent=classifier)
write = Task(
    description="Write a summary using the research",
    expected_output="Summary",
    agent=task_handler,
    context=[research],   # <- output of `research` flows in here
)

crew = Crew(
    agents=[classifier, task_handler],
    tasks=[research, write],
    process=Process.sequential,
)
crew.kickoff()
```

This is the CrewAI equivalent of LangGraph's plain `add_edge(a, b)` chain — no
router, just "run these tasks in order."

---

## 7. Key Takeaway

| CrewAI Term | Meaning |
|---|---|
| **Agent** | An LLM-backed worker defined by role, goal, and backstory |
| **Task** | A single piece of work assigned to an agent |
| **Crew** | The full team of agents and their tasks |
| **Process** | How tasks are ordered (`sequential` or `hierarchical`) |
| **Conditional Task** | A task that runs only when its condition is true |

In simple words:

> CrewAI lets you build AI workflows where each worker is an **agent** with a
> role, each piece of work is a **task**, and the **crew** coordinates them to
> reach a final result.

---

## 8. Why CrewAI is Useful

Use CrewAI when:

- You want to model a workflow as a **team of specialists**
- Each step is better described as a *role and goal* than as code
- You want agents to **delegate** and collaborate (hierarchical process)
- You want fast setup with sensible multi-agent defaults

LangGraph gives you fine-grained control over **graph structure and state**.
CrewAI gives you a higher-level, **role-first** abstraction. For deterministic,
branching logic you control yourself, LangGraph is clearer; for collaborative
LLM "teams," CrewAI is faster to express.
