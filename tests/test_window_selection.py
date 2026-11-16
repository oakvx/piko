"""Background window selection must never bypass fresh grants or review."""
from __future__ import annotations

import pytest

from piko.contracts import Action, Expectation, Grant, Observation, Plan, UIElement
from piko.memory import LocalMemory
from piko.orchestrator import Agent
from piko.permissions import PermissionManager


class SelectedBackgroundDesktop:
    def __init__(self):
        self.focused = False
        self.activated = 0
        self.invoked = 0

    def observe(self, include_image=False):
        raise AssertionError("Cannot inspect Piko's foreground window")

    def observe_window(self, hwnd, executable, include_image=False):
        assert hwnd == 1234 and executable == "notepad.exe"
        return Observation(executable=executable, window_title="Approved Notepad",
                           process_id=99, process_started_at=1.5,
                           window_handle=1234,
                           elements=[UIElement(automation_id="Save", name="Save")])

    def activate_window(self, expected):
        assert expected.window_handle == 1234
        assert expected.process_id == 99 and expected.process_started_at == 1.5
        self.focused = True
        self.activated += 1

    def execute_observed(self, action, expected):
        assert self.focused
        assert expected.window_handle == 1234
        self.invoked += 1

    def begin_session(self):
        pass

    def emergency_release(self):
        pass


class Planner:
    async def plan(self, goal, observation, scene_summary=None):
        assert observation.window_handle == 1234
        return Plan(objective=goal, explanation="Reviewed scoped UIA action",
                    actions=[Action(kind="ui.click", automation_id="Save",
                                    expected=Expectation(automation_id="Save", property="exists"))])


@pytest.mark.asyncio
async def test_background_window_requires_review_then_activates_only_approved_window(tmp_path):
    desktop = SelectedBackgroundDesktop()
    memory = LocalMemory(tmp_path / "selected.sqlite")
    try:
        permissions = PermissionManager()
        agent = Agent(desktop, Planner(), memory, permissions)
        session = agent.create("Click Save", "notepad.exe",
                               target_window_handle=1234, allow_activate=True)
        permissions.grant(Grant(executable="notepad.exe", session_id=session.id))
        prepared = await agent.prepare(session.id)
        assert prepared.state.value == "waiting_for_user"
        assert desktop.activated == 0 and desktop.invoked == 0
        result = await agent.run(session.id)
        assert result.state.value == "completed"
        assert desktop.activated == 1 and desktop.invoked == 1
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_background_selection_cannot_act_without_grant(tmp_path):
    desktop = SelectedBackgroundDesktop()
    memory = LocalMemory(tmp_path / "ungranted.sqlite")
    try:
        agent = Agent(desktop, Planner(), memory, PermissionManager())
        session = agent.create("Click Save", "notepad.exe",
                               target_window_handle=1234, allow_activate=True)
        with pytest.raises(PermissionError):
            await agent.prepare(session.id)
        assert desktop.activated == 0 and desktop.invoked == 0
    finally:
        memory.close()


def test_cannot_approve_activation_without_explicit_window(tmp_path):
    memory = LocalMemory(tmp_path / "invalid.sqlite")
    try:
        agent = Agent(SelectedBackgroundDesktop(), Planner(), memory, PermissionManager())
        with pytest.raises(ValueError, match="selected application window"):
            agent.create("Click Save", "notepad.exe", allow_activate=True)
    finally:
        memory.close()
