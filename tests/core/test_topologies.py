from typing import TypedDict
from src.core.topologies import sequential_pipeline, critique_loop, planner_executor


class SeqState(TypedDict, total=False):
    trace: list


def test_sequential_runs_first_then_second():
    g = sequential_pipeline(
        SeqState,
        first=lambda s: {"trace": s.get("trace", []) + ["first"]},
        second=lambda s: {"trace": s.get("trace", []) + ["second"]},
    )
    assert g.invoke({"trace": []})["trace"] == ["first", "second"]


class LoopState(TypedDict, total=False):
    round: int
    verdict: str
    status: str
    history: list


def test_critique_loop_stops_on_pass():
    def reviewer(s):
        return {"verdict": "pass", "history": s.get("history", []) + [s["round"]]}
    def route(s):
        return "approve" if s["verdict"] == "pass" else "revise"
    g = critique_loop(LoopState, generator=lambda s: {}, reviewer=reviewer,
                      route_after_review=route, approved_status="done")
    out = g.invoke({"round": 1, "history": []})
    assert out["status"] == "done" and out["round"] == 1


def test_critique_loop_escalates_at_max_rounds():
    max_rounds = 3
    def reviewer(s):
        return {"verdict": "revise"}
    def route(s):
        if s["verdict"] == "pass":
            return "approve"
        return "escalate" if s["round"] >= max_rounds else "revise"
    g = critique_loop(LoopState, generator=lambda s: {}, reviewer=reviewer,
                      route_after_review=route, escalated_status="esc")
    out = g.invoke({"round": 1})
    assert out["status"] == "esc" and out["round"] == 3


def test_input_guard_short_circuits():
    def guard(s):
        return {"status": "escalated"}
    g = critique_loop(LoopState, generator=lambda s: {"round": 99}, reviewer=lambda s: {},
                      route_after_review=lambda s: "approve", input_guard=guard,
                      escalated_status="blocked")
    out = g.invoke({"round": 1})
    assert out["status"] == "blocked" and out.get("round") == 1  # generator never ran


class PlanState(TypedDict, total=False):
    tasks: list
    artifacts: list


def test_planner_executor_runs_executor_per_selected_task():
    g = planner_executor(
        PlanState,
        planner=lambda s: {"tasks": [{"id": 1, "mode": "auto"}, {"id": 2, "mode": "human"}]},
        executor=lambda task, s: {"for": task["id"]},
        task_selector=lambda tasks: [t for t in tasks if t["mode"] == "auto"],
    )
    out = g.invoke({})
    assert out["artifacts"] == [{"for": 1}]  # only the auto task; none dropped
