from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src import guards
from src.agents import build_drafter, build_reviewer
from src.config import AppConfig
from src.schemas import GraphState


def initial_state(member_message: str, case_notes: str) -> dict:
    return {
        "member_message": member_message,
        "case_notes": case_notes,
        "round": 1,
        "history": [],
    }


def build_app(config: AppConfig, drafter_model, reviewer_model):
    drafter = build_drafter(drafter_model, config.drafter.system_prompt)
    reviewer = build_reviewer(reviewer_model, config.reviewer.system_prompt)
    max_rounds = config.loop.max_rounds
    inj_patterns = config.guards.injection_patterns
    cred_patterns = config.guards.credential_patterns

    def guard_input_node(state: GraphState) -> dict:
        hits = guards.scan_input(state["member_message"], inj_patterns) + guards.scan_input(
            state["case_notes"], inj_patterns
        )
        if hits:
            return {
                "status": "escalated",
                "verdict": "revise",
                "feedback": [
                    {"item": "prompt_injection", "reason": f"Injection patterns detected: {hits}"}
                ],
            }
        return {}

    def route_after_guard(state: GraphState) -> str:
        return "escalate" if state.get("status") == "escalated" else "drafter"

    def drafter_node(state: GraphState) -> dict:
        draft = drafter(state["member_message"], state["case_notes"], state.get("feedback"))
        return {"draft": draft}

    def reviewer_node(state: GraphState) -> dict:
        verdict_obj = reviewer(state["draft"], state["case_notes"])
        failed = [fi.model_dump() for fi in verdict_obj.failed_items]
        verdict = "pass" if (verdict_obj.verdict == "pass" and not failed) else "revise"

        cred_hits = guards.scan_output(state["draft"], cred_patterns)
        if cred_hits:
            verdict = "revise"
            failed = failed + [
                {"item": "credential_request", "reason": f"Draft requests prohibited info: {cred_hits}"}
            ]

        record = {
            "round": state["round"],
            "draft": state["draft"],
            "verdict": verdict,
            "failed_items": failed,
        }
        return {
            "verdict": verdict,
            "feedback": failed,
            "history": state.get("history", []) + [record],
        }

    def route_after_review(state: GraphState) -> str:
        if state["verdict"] == "pass":
            return "approve"
        if state["round"] >= max_rounds:
            return "escalate"
        return "revise"

    def increment_node(state: GraphState) -> dict:
        return {"round": state["round"] + 1}

    def approve_node(state: GraphState) -> dict:
        return {"status": "pending_human_review"}

    def escalate_node(state: GraphState) -> dict:
        return {"status": "escalated"}

    g = StateGraph(GraphState)
    g.add_node("guard_input", guard_input_node)
    g.add_node("drafter", drafter_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("increment", increment_node)
    g.add_node("approve", approve_node)
    g.add_node("escalate", escalate_node)

    g.add_edge(START, "guard_input")
    g.add_conditional_edges("guard_input", route_after_guard,
                            {"escalate": "escalate", "drafter": "drafter"})
    g.add_edge("drafter", "reviewer")
    g.add_conditional_edges("reviewer", route_after_review,
                            {"approve": "approve", "escalate": "escalate", "revise": "increment"})
    g.add_edge("increment", "drafter")
    g.add_edge("approve", END)
    g.add_edge("escalate", END)
    return g.compile()
