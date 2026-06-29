from __future__ import annotations
from typing import TypedDict
from pydantic import BaseModel, Field


class ContentInput(BaseModel):
    product_name: str = Field(min_length=1)
    spec_sheet: str = Field(min_length=1)


class ResearchNotes(BaseModel):
    facts: list[str]
    differentiators: list[str]
    missing: list[str] = Field(default_factory=list)


class WriterOutput(BaseModel):
    copy: str
    highlights: list[str]


class ContentResult(BaseModel):
    notes: ResearchNotes
    copy: str
    highlights: list[str]
    missing: list[str] = Field(default_factory=list)

    @classmethod
    def from_state(cls, final: dict) -> "ContentResult":
        notes: ResearchNotes = final["notes"]
        writer: WriterOutput = final["writer"]
        return cls(notes=notes, copy=writer.copy, highlights=writer.highlights, missing=notes.missing)


class ContentState(TypedDict, total=False):
    product_name: str
    spec_sheet: str
    notes: ResearchNotes
    writer: WriterOutput
