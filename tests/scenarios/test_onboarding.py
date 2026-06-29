from src.scenarios.onboarding.schemas import TaskList, Task, Artifact
from src.scenarios.onboarding.service import OnboardingService
from tests.stub_model import StubModel


def test_executor_runs_only_auto_tasks():
    planner = StubModel(structured=TaskList(tasks=[
        Task(step=1, description="Verify cert", mode="auto"),
        Task(step=2, description="Manager sign-off", mode="human"),
    ]))
    executor = StubModel(structured=Artifact(step=1, output="Checklist: verify forklift cert on file"))
    svc = OnboardingService.from_models(planner, executor)
    result = svc.run("Onboard 2 forklift associates Monday", "warehouse associate")
    assert [t.step for t in result.tasks] == [1, 2]      # both planned, none dropped
    assert [a.step for a in result.artifacts] == [1]     # only the auto task executed
