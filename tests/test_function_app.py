"""Azure Functions entry-point tests.

`@app.route` returns a FunctionBuilder whose __call__ delegates to the wrapped
function, so the handlers are invoked directly with constructed HttpRequests.
Importing function_app builds the real service from config.yaml - keyless and
network-free by design (that is itself the deploy-time-validation behavior).
"""

from __future__ import annotations

import json

import azure.functions as func

import function_app


def _post(payload: bytes) -> func.HttpRequest:
    return func.HttpRequest(method="POST", url="/api/draft", body=payload)


def test_health_returns_json():
    resp = function_app.health(func.HttpRequest(method="GET", url="/api/health", body=b""))
    assert resp.status_code == 200
    assert json.loads(resp.get_body()) == {"status": "ok"}


def test_invalid_json_returns_400_with_valid_body():
    resp = function_app.draft(_post(b"not json"))
    assert resp.status_code == 400
    assert "detail" in json.loads(resp.get_body())


def test_missing_field_returns_422_with_valid_json_body():
    # Regression for the f-string-built body: a ValidationError's string
    # contains newlines and quotes that used to break the JSON syntactically.
    resp = function_app.draft(_post(json.dumps({"member_message": "only one"}).encode()))
    assert resp.status_code == 422
    body = json.loads(resp.get_body())
    assert body["detail"].startswith("Invalid input:")


def test_unexpected_service_error_returns_generic_503(monkeypatch):
    class _BrokenService:
        def run(self, member_message, case_notes):
            raise RuntimeError("secret internals: /etc/config leaked")

    monkeypatch.setattr(function_app, "_service", _BrokenService())
    resp = function_app.draft(
        _post(json.dumps({"member_message": "m", "case_notes": "n"}).encode())
    )
    assert resp.status_code == 503
    body = json.loads(resp.get_body())
    assert body["detail"] == "Agent run failed"
    assert "secret internals" not in resp.get_body().decode()
