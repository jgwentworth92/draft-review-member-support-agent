from __future__ import annotations
from typing import TypedDict, Literal
from pydantic import BaseModel, Field


class PolicyInput(BaseModel):
    question: str = Field(min_length=1)
    handbook: str = Field(min_length=1)


class Snippet(BaseModel):
    text: str
    section: str
    confidence: Literal["high", "low"] = "high"


class RetrievedSnippets(BaseModel):
    snippets: list[Snippet] = Field(default_factory=list)


class ResponderOutput(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    found: bool


class PolicyResult(BaseModel):
    answer: str
    citations: list[str]
    found: bool
    confidence: str

    @classmethod
    def from_state(cls, final: dict) -> "PolicyResult":
        responder: ResponderOutput = final["responder"]
        snippets = final["retrieved"].snippets
        confidence = "low" if (not snippets or any(s.confidence == "low" for s in snippets)) else "high"
        return cls(answer=responder.answer, citations=responder.citations,
                   found=responder.found, confidence=confidence)


class PolicyState(TypedDict, total=False):
    question: str
    handbook: str
    retrieved: RetrievedSnippets
    responder: ResponderOutput
