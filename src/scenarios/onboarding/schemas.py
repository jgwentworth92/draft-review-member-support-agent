from __future__ import annotations
from typing import TypedDict, Literal
from pydantic import BaseModel, Field


class OnboardingInput(BaseModel):
    request: str = Field(min_length=1)
    role: str = Field(min_length=1)


class Task(BaseModel):
    step: int
    description: str
    depends_on: list[int] = Field(default_factory=list)
    mode: Literal["auto", "human"] = "auto"


class TaskList(BaseModel):
    tasks: list[Task]


class Artifact(BaseModel):
    step: int
    output: str


class OnboardingResult(BaseModel):
    tasks: list[Task]
    artifacts: list[Artifact]

    @classmethod
    def from_state(cls, final: dict) -> "OnboardingResult":
        return cls(tasks=final["tasks"], artifacts=final["artifacts"])


class OnboardingState(TypedDict, total=False):
    request: str
    role: str
    tasks: list
    artifacts: list
