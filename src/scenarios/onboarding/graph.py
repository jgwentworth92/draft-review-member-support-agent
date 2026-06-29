from __future__ import annotations
from src.core.topologies import planner_executor
from src.scenarios.onboarding.agents import build_planner, build_executor
from src.scenarios.onboarding.schemas import OnboardingState


def initial_state(request, role):
    return {"request": request, "role": role}


def build_app(config, planner_model, executor_model):
    planner = build_planner(planner_model, config.planner.system_prompt)
    executor = build_executor(executor_model, config.executor.system_prompt)

    def planner_node(state):
        return {"tasks": planner(state["request"], state["role"]).tasks}

    def exec_one(task, state):
        return executor(task, state)

    return planner_executor(
        OnboardingState, planner=planner_node, executor=exec_one,
        task_selector=lambda tasks: [t for t in tasks if t.mode == "auto"],
    )
