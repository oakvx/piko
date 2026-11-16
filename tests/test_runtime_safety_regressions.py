"""Regression tests for crash recovery, native dispatch and Teach privacy."""
from __future__ import annotations

import asyncio
import json
import threading

import pytest

from piko.contracts import Action, Expectation, Grant, Observation, Plan, Session, SessionState, UIElement
from piko.memory import LocalMemory
from piko.orchestrator import Agent
from piko.permissions import PermissionManager
from piko.teach import TeachRecorder


class BlockingDesktop:
    def __init__(self):
        self.started = threading.Event()
        self.release_action = threading.Event()
        self.releases = 0

    def observe(self, include_image=False):
        return Observation(
            window_title="Demo",
            process_id=1,
            executable="demo.exe",
            elements=[UIElement(automation_id="go", control_type="Button")],
        )

    def execute(self, action):
        self.started.set()
        self.release_action.wait(timeout=3)

    def emergency_release(self):
        self.releases += 1


class OneStepPlanner:
    async def plan(self, objective, observation, scene_summary=None):
        return Plan(
            objective=objective,
            explanation="Controlled test action",
            actions=[
                Action(
                    kind="ui.click",
                    automation_id="go",
                    timeout_seconds=0.1,
                    expected=Expectation(automation_id="go", property="exists"),
                )
            ],
        )


@pytest.mark.asyncio
async def test_timed_out_native_dispatch_retains_lock_until_worker_returns(tmp_path):
    desktop = BlockingDesktop()
    store = LocalMemory(tmp_path / "timeout.db")
    agent = Agent(desktop, OneStepPlanner(), store, PermissionManager())
    session = agent.create("Run fixture", "demo.exe")
    agent.permissions.grant(Grant(executable="demo.exe", session_id=session.id))
    await agent.prepare(session.id)
    task = asyncio.create_task(agent.run(session.id))
    try:
        assert await asyncio.to_thread(desktop.started.wait, 2)
        await asyncio.sleep(0.2)  # The action's 0.1s timeout already expired.
        assert not task.done(), "Must not release ownership while native input is still running"
        assert desktop.releases == 0
    finally:
        desktop.release_action.set()
    result = await asyncio.wait_for(task, timeout=2)
    assert result.state == SessionState.FAILED
    assert desktop.releases == 1
    store.close()


def test_restart_invalidates_unapproved_and_reviewed_sessions(tmp_path):
    path = tmp_path / "crash.db"
    initial = LocalMemory(path)
    initial.save(Session(objective="idle", app_executable="demo.exe"))
    initial.save(Session(
        objective="reviewed",
        app_executable="demo.exe",
        state=SessionState.WAITING_FOR_USER,
    ))
    initial.close()
    recovered = LocalMemory(path)
    agent = Agent(BlockingDesktop(), OneStepPlanner(), recovered, PermissionManager())
    assert len(agent.sessions) == 2
    assert all(item.state == SessionState.FAILED for item in agent.sessions.values())
    assert all("not automatically resumed" in item.error for item in agent.sessions.values())
    recovered.close()


class PrivateDesktop:
    def observe(self, include_image=False):
        return Observation(
            window_title="Confidential Alice",
            process_id=21,
            executable="demo.exe",
            elements=[
                UIElement(
                    automation_id="name::Text::Alice Name",
                    name="Alice Name",
                    control_type="Text",
                    value="EXPOSED-SECRET",
                ),
                UIElement(automation_id="Save", name="Save", control_type="Button"),
            ],
            image_base64="YQ==" if include_image else None,
        )


@pytest.mark.asyncio
async def test_teach_manifest_redacts_text_values_and_dynamic_ids(tmp_path):
    recorder = TeachRecorder(PrivateDesktop(), tmp_path / "recordings")
    identifier = await recorder.start("demo.exe", seconds=1)
    for _ in range(40):
        if list((recorder.root / identifier).glob("frame-*.png")):
            break
        await asyncio.sleep(0.025)
    manifest = await recorder.stop()
    assert manifest["frames"] >= 1
    contents = json.dumps(manifest)
    assert "EXPOSED-SECRET" not in contents
    assert "Confidential Alice" not in contents
    assert "Alice Name" not in contents
    assert "Save" in contents
