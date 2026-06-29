from __future__ import annotations
from src.core.topologies import sequential_pipeline
from src.scenarios.policy.agents import build_retriever, build_responder
from src.scenarios.policy.schemas import PolicyState


def initial_state(question, handbook):
    return {"question": question, "handbook": handbook}


def build_app(config, retriever_model, responder_model):
    retriever = build_retriever(retriever_model, config.retriever.system_prompt)
    responder = build_responder(responder_model, config.responder.system_prompt)

    def retrieve_node(state):
        return {"retrieved": retriever(state["question"], state["handbook"])}

    def respond_node(state):
        return {"responder": responder(state["question"], state["retrieved"])}

    return sequential_pipeline(PolicyState, first=retrieve_node, second=respond_node)
