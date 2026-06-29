from __future__ import annotations
from langgraph.graph import END, START, StateGraph


def sequential_pipeline(state_type, *, first, second):
    g = StateGraph(state_type)
    g.add_node("first", first)
    g.add_node("second", second)
    g.add_edge(START, "first")
    g.add_edge("first", "second")
    g.add_edge("second", END)
    return g.compile()


def critique_loop(
    state_type, *, generator, reviewer, route_after_review,
    input_guard=None, approved_status="approved", escalated_status="escalated", retry_policy=None,
):
    g = StateGraph(state_type)
    g.add_node("generator", generator, retry_policy=retry_policy)
    g.add_node("reviewer", reviewer, retry_policy=retry_policy)
    g.add_node("increment", lambda s: {"round": s["round"] + 1})
    g.add_node("approve", lambda s: {"status": approved_status})
    g.add_node("escalate", lambda s: {"status": escalated_status})

    if input_guard is not None:
        g.add_node("guard", input_guard)
        g.add_edge(START, "guard")
        g.add_conditional_edges(
            "guard",
            lambda s: "escalate" if s.get("status") == "escalated" else "generator",
            {"escalate": "escalate", "generator": "generator"},
        )
    else:
        g.add_edge(START, "generator")

    g.add_edge("generator", "reviewer")
    g.add_conditional_edges(
        "reviewer", route_after_review,
        {"approve": "approve", "escalate": "escalate", "revise": "increment"},
    )
    g.add_edge("increment", "generator")
    g.add_edge("approve", END)
    g.add_edge("escalate", END)
    return g.compile()


def planner_executor(state_type, *, planner, executor, task_selector, retry_policy=None):
    g = StateGraph(state_type)
    g.add_node("planner", planner, retry_policy=retry_policy)

    def execute_all(state) -> dict:
        selected = task_selector(state["tasks"])
        return {"artifacts": [executor(task, state) for task in selected]}

    g.add_node("executor", execute_all, retry_policy=retry_policy)
    g.add_edge(START, "planner")
    g.add_edge("planner", "executor")
    g.add_edge("executor", END)
    return g.compile()
