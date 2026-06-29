from pydantic import BaseModel
from src.core.nodes import text_agent_node, structured_agent_node
from tests.stub_model import StubModel  # existing helper


class Verdict(BaseModel):
    ok: bool


def test_text_agent_node_formats_and_returns_content():
    model = StubModel(reply="hello world")
    node = text_agent_node(model, "SYS", lambda x: f"INPUT:{x}")
    assert node("hi") == "hello world"
    assert "INPUT:hi" in model.last_human  # prompt was formatted and sent


def test_structured_agent_node_returns_schema_object():
    model = StubModel(structured=Verdict(ok=True))
    node = structured_agent_node(model, Verdict, "SYS", lambda x: x)
    out = node("anything")
    assert isinstance(out, Verdict) and out.ok is True
