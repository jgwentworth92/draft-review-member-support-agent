from src.scenarios.content.schemas import ResearchNotes, WriterOutput
from src.scenarios.content.service import ContentService
from tests.stub_model import StubModel


def test_content_pipeline_uses_only_researched_facts():
    researcher = StubModel(structured=ResearchNotes(facts=["1.5L borosilicate glass"],
                                                    differentiators=["cork lid"], missing=[]))
    writer = StubModel(structured=WriterOutput(copy="A 1.5L borosilicate carafe with a cork lid.",
                                               highlights=["1.5L", "cork lid"]))
    svc = ContentService.from_models(researcher, writer)
    result = svc.run("Pour-Over Carafe", "Borosilicate, 1.5L, cork lid")
    assert "1.5L" in result.copy
    assert result.missing == []
    assert result.highlights == ["1.5L", "cork lid"]


def test_content_flags_missing_specs():
    researcher = StubModel(structured=ResearchNotes(facts=[], differentiators=[], missing=["capacity"]))
    writer = StubModel(structured=WriterOutput(copy="...", highlights=[]))
    svc = ContentService.from_models(researcher, writer)
    assert svc.run("X", "no capacity given").missing == ["capacity"]
