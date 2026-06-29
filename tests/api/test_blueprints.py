from src.api import blueprints


def test_all_scenario_routes_registered():
    routes = blueprints.registered_routes()
    assert {"content", "quality", "draft", "onboarding", "policy"} <= routes
