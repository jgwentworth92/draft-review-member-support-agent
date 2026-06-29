import json
from pydantic import BaseModel
from src.api.routes import run_json_route


class In(BaseModel):
    a: str


class Out(BaseModel):
    echoed: str


class FakeService:
    def run(self, a):
        return Out(echoed=a)


class FakeReq:
    def __init__(self, body):
        self._body = body
    def get_json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def call(body):
    return run_json_route(lambda: FakeService(), In, FakeReq(body),
                          map_input=lambda m: {"a": m.a})


def test_valid_request_returns_200():
    resp = call({"a": "hi"})
    assert resp.status_code == 200
    assert json.loads(resp.get_body())["echoed"] == "hi"


def test_invalid_json_returns_400():
    assert call(None).status_code == 400


def test_schema_violation_returns_422():
    assert call({"wrong": "x"}).status_code == 422
