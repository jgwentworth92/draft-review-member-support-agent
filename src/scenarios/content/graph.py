from __future__ import annotations
from src.core.topologies import sequential_pipeline
from src.scenarios.content.agents import build_researcher, build_writer
from src.scenarios.content.schemas import ContentState


def initial_state(product_name: str, spec_sheet: str) -> dict:
    return {"product_name": product_name, "spec_sheet": spec_sheet}


def build_app(config, researcher_model, writer_model):
    researcher = build_researcher(researcher_model, config.researcher.system_prompt)
    writer = build_writer(writer_model, config.writer.system_prompt)

    def research_node(state):
        return {"notes": researcher(state["product_name"], state["spec_sheet"])}

    def write_node(state):
        return {"writer": writer(state["notes"])}

    return sequential_pipeline(ContentState, first=research_node, second=write_node)
