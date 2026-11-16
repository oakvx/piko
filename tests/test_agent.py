from pathlib import Path

import pytest

from piko.contracts import Action, ActionKind, Expectation, Grant, Observation, Plan, SessionState, UIElement
from piko.memory import LocalMemory
from piko.orchestrator import Agent
from piko.permissions import PermissionManager


class FakeDesktop:
    """Test fixture only: deterministic UIA behavior without external Windows hardware."""
    def __init__(self):
        self.executable = "demo.exe"
        self.name = ""
        self.status = "Waiting"
        self.fail_save = False
        self.released = 0
        self.calls = []

    def observe(self, include_image=False):
        return Observation(window_title="Testbench", executable=self.executable, process_id=77,
            elements=[UIElement(automation_id="NameInput", control_type="Edit", value=self.name),
                      UIElement(automation_id="SaveButton", control_type="Button"),
                      UIElement(automation_id="StatusLabel", control_type="Text", value=self.status)])

    def execute(self, action):
        self.calls.append(action.kind.value)
        if action.kind == ActionKind.SET_TEXT:
            self.name = action.text
        elif action.kind == ActionKind.CLICK and not self.fail_save:
            self.status = f"Saved: {self.name}"

    def emergency_release(self):
        self.released += 1


class TestPlanner:
    async def plan(self, objective, observation, scene_summary=None):
        return Plan(objective=objective, explanation="Populate the name then save",
            actions=[
                Action(kind=ActionKind.SET_TEXT, automation_id="NameInput", text="Ada",
                       expected=Expectation(automation_id="NameInput", property="text_equals", value="Ada")),
                Action(kind=ActionKind.CLICK, automation_id="SaveButton",
                       expected=Expectation(automation_id="StatusLabel", property="text_equals", value="Saved: Ada"))])


@pytest.fixture
def setup(tmp_path):
    desktop = FakeDesktop()
    planner = TestPlanner()
    store = LocalMemory(tmp_path / "db.sqlite")
    perms = PermissionManager()
    agent = Agent(desktop, planner, store, perms)
    yield agent, desktop, store, perms
    store.close()


@pytest.mark.asyncio
async def test_end_to_end_plan_execute_verify(setup):
    agent, desktop, store, perms = setup
    session = agent.create("Save Ada", "demo.exe")
    perms.grant(Grant(executable="demo.exe", session_id=session.id))
    planned = await agent.prepare(session.id)
    assert planned.state == SessionState.WAITING_FOR_USER
    assert desktop.calls == []
    result = await agent.run(session.id)
    assert result.state == SessionState.COMPLETED
    assert result.next_action == 2
    assert desktop.status == "Saved: Ada"
    assert desktop.released == 1
    events = store.list_events(session.id)
    assert [event['type'] for event in events].count('verification.completed') == 2
    assert [event['type'] for event in events].count('action.verified') == 2
    assert all('Ada' not in str(event['payload']) for event in events)


@pytest.mark.asyncio
async def test_no_permission_no_inputs(setup):
    agent, desktop, _, _ = setup
    session = agent.create("Save Ada", "demo.exe")
    with pytest.raises(PermissionError):
        await agent.prepare(session.id)
    assert desktop.calls == []
    assert agent.sessions[session.id].state == SessionState.FAILED


@pytest.mark.asyncio
async def test_ui_switch_during_execution_stops(setup):
    agent, desktop, store, perms = setup
    session = agent.create("Save Ada", "demo.exe")
    perms.grant(Grant(executable="demo.exe"))
    await agent.prepare(session.id)
    desktop.executable = "other.exe"
    done = await agent.run(session.id)
    assert done.state == SessionState.FAILED
    assert desktop.calls == []
    assert desktop.released == 1
    failed = [event for event in store.list_events(session.id)
              if event["type"] == "action.failed"]
    assert len(failed) == 1
    assert failed[0]["payload"] == {
        "action": "ui.set_text", "index": 0, "phase": "preflight",
        "reason": "RuntimeError",
    }


@pytest.mark.asyncio
async def test_unsupported_outcome_fails_not_faked(setup):
    agent, desktop, _, perms = setup
    session = agent.create("Save Ada", "demo.exe")
    perms.grant(Grant(executable="demo.exe"))
    await agent.prepare(session.id)
    desktop.fail_save = True
    # Small timeout for verification failure test.
    plan = agent.sessions[session.id].plan
    plan.actions[1].timeout_seconds = 0.1
    done = await agent.run(session.id)
    assert done.state == SessionState.FAILED
    assert done.next_action == 1
    assert done.error.startswith("Action 2 not verified")
    assert desktop.released == 1


@pytest.mark.asyncio
async def test_cancellation_before_dispatch(setup):
    agent, desktop, _, perms = setup
    session = agent.create("Save Ada", "demo.exe")
    perms.grant(Grant(executable="demo.exe"))
    await agent.prepare(session.id)
    agent.stop(session.id)
    assert agent.sessions[session.id].state == SessionState.CANCELLED
    assert desktop.calls == []


def test_memory_crash_recovery(tmp_path):
    store = LocalMemory(tmp_path / "state.sqlite")
    from piko.contracts import Session
    session = Session(objective="task", app_executable="demo.exe", state=SessionState.EXECUTING)
    store.save(session)
    store.close()
    recovered = LocalMemory(tmp_path / "state.sqlite")
    assert recovered.list_sessions()[0].state == SessionState.FAILED
    assert "not automatically resumed" in recovered.list_sessions()[0].error
    recovered.close()
