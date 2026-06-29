from src.scenarios.policy.schemas import RetrievedSnippets, Snippet, ResponderOutput
from src.scenarios.policy.service import PolicyService
from tests.stub_model import StubModel


def test_policy_answers_with_citation_when_found():
    retriever = StubModel(structured=RetrievedSnippets(
        snippets=[Snippet(text="Full-time employees accrue 18 days/year.", section="§4.2", confidence="high")]))
    responder = StubModel(structured=ResponderOutput(answer="18 days per year.", citations=["§4.2"], found=True))
    svc = PolicyService.from_models(retriever, responder)
    r = svc.run("How many PTO days per year?", "<handbook>")
    assert r.found and r.citations == ["§4.2"] and r.confidence == "high"


def test_policy_returns_not_found_when_absent():
    retriever = StubModel(structured=RetrievedSnippets(snippets=[]))
    responder = StubModel(structured=ResponderOutput(answer="Not found in handbook.", citations=[], found=False))
    svc = PolicyService.from_models(retriever, responder)
    r = svc.run("Parental leave?", "<handbook>")
    assert r.found is False and r.confidence == "low"
