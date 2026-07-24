# Learn LangGraph: Nodes, Edges, Conditional Edges, and State

## 1. What is LangGraph?

LangGraph is a framework used to build **stateful AI workflows** as a graph.

In a normal chain, steps usually run one after another:

```text
Step 1 → Step 2 → Step 3 → END
```

In LangGraph, the workflow can branch, loop, and make decisions:

```text
START → Process Input → Decide Intent → Add Task / Complete Task / Summarize → END
```

This makes LangGraph useful for **agents**, **multi-agent systems**, **RAG workflows**, and **complex AI applications**.

---

## 2. Core Concepts

| Concept | Simple Meaning | Example |
|---|---|---|
| **Node** | A function or action | Add task, complete task, summarize tasks |
| **Edge** | A connection between nodes | START → process_input |
| **Conditional Edge** | A decision-based route | If intent is `add_task`, go to add task node |
| **State** | Shared data passed between nodes | User input, intent, response, task list |
| **START** | Beginning of the graph | First execution point |
| **END** | End of the graph | Workflow finishes |

---

## 3. Simple Flow Diagram

```text
START
  |
  v
process_input node
  |
  |-- if intent == add_task ---------> add_task node ---------> END
  |
  |-- if intent == complete_task ----> complete_task node ----> END
  |
  |-- otherwise ---------------------> summarize_tasks node -> END
```

---

## 4. LangGraph Example Code

```python
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END


# 1. Define State
class TaskState(TypedDict):
    user_input: str
    intent: str
    response: str


# 2. Node: understand user intent
def process_input(state: TaskState):
    text = state["user_input"].lower()

    if "add" in text:
        intent = "add_task"
    elif "complete" in text or "done" in text:
        intent = "complete_task"
    else:
        intent = "summarize"

    return {"intent": intent}


# 3. Node: add task
def add_task(state: TaskState):
    return {"response": "Task added successfully."}


# 4. Node: complete task
def complete_task(state: TaskState):
    return {"response": "Task marked as completed."}


# 5. Node: summarize tasks
def summarize_tasks(state: TaskState):
    return {"response": "Here is the summary of your tasks."}


# 6. Conditional edge / router
def route_intent(state: TaskState) -> Literal["add_task", "complete_task", "summarize_tasks"]:
    if state["intent"] == "add_task":
        return "add_task"
    elif state["intent"] == "complete_task":
        return "complete_task"
    else:
        return "summarize_tasks"


# 7. Build graph
builder = StateGraph(TaskState)

builder.add_node("process_input", process_input)
builder.add_node("add_task", add_task)
builder.add_node("complete_task", complete_task)
builder.add_node("summarize_tasks", summarize_tasks)

# Normal edge: START -> process_input
builder.add_edge(START, "process_input")

# Conditional edge: process_input -> correct action node
builder.add_conditional_edges("process_input", route_intent)

# Normal edges: action nodes -> END
builder.add_edge("add_task", END)
builder.add_edge("complete_task", END)
builder.add_edge("summarize_tasks", END)

graph = builder.compile()


# 8. Run graph
result = graph.invoke({
    "user_input": "add buy milk",
    "intent": "",
    "response": ""
})

print(result)
```

---

## 5. Expected Output

If the input is:

```python
"add buy milk"
```

The graph flow is:

```text
START → process_input → add_task → END
```

Output will be similar to:

```python
{
    "user_input": "add buy milk",
    "intent": "add_task",
    "response": "Task added successfully."
}
```

---

## 6. Same Graph Using `set_entry_point()`

You may also see older or alternative examples using:

```python
builder.set_entry_point("process_input")
```

This is equivalent to:

```python
builder.add_edge(START, "process_input")
```

So these two styles do the same job.

### Style 1: START / END style

```python
builder.add_edge(START, "process_input")
builder.add_edge("add_task", END)
```

### Style 2: set_entry_point style

```python
builder.set_entry_point("process_input")
builder.add_edge("add_task", END)
```

The `START` / `END` style is usually clearer for learning because it shows the full graph execution path explicitly.

---

## 7. Key Takeaway

| LangGraph Term | Meaning |
|---|---|
| **Node** | A Python function that performs work |
| **Edge** | A fixed connection between two nodes |
| **Conditional Edge** | A router that decides the next node dynamically |
| **State** | Shared data that flows through the graph |
| **Graph** | The full workflow structure |

In simple words:

> LangGraph lets you build AI workflows where each task is a node, each connection is an edge, and the state is shared memory between nodes.

---

## 8. Why LangGraph is Useful

LangGraph is useful when your AI workflow is not just one straight chain.

Use LangGraph when you need:

- Multiple possible paths
- Decision-making between steps
- Shared state
- Loops
- Human approval steps
- Multi-agent collaboration
- Complex RAG pipelines
- Long-running agent workflows

For simple one-step LLM calls, LangGraph may be unnecessary. For complex agentic systems, it gives you better control and structure.
