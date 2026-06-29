from __future__ import annotations


class PipelineService:
    """Holds a compiled graph built ONCE; runs many inputs through it.

    Scenario subclasses build `graph` from a core topology builder and pass it to
    super().__init__, then expose a typed `run(...)` that maps domain input ->
    init state and final state -> a typed result.
    """

    def __init__(self, graph):
        self.graph = graph

    def invoke(self, init_state: dict) -> dict:
        return self.graph.invoke(init_state)
