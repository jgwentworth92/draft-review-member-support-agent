from typing import TypedDict
from src.core.service import PipelineService
from src.core.topologies import sequential_pipeline


class S(TypedDict, total=False):
    x: int


def test_service_invokes_its_graph_and_is_reusable():
    graph = sequential_pipeline(S, first=lambda s: {"x": s["x"] + 1}, second=lambda s: {"x": s["x"] * 2})
    svc = PipelineService(graph)
    assert svc.invoke({"x": 1})["x"] == 4
    assert svc.invoke({"x": 5})["x"] == 12  # reusable across calls
