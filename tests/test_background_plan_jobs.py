"""Background local planning is UI-pollable, auth gated and never dispatches input."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from piko.api import create_app
from piko.contracts import Action, Expectation, Observation, Plan, UIElement


class DemoDesktop:
    def __init__(self):
        self.input_calls = 0

    def observe(self, include_image: bool = False):
        return Observation(executable="demo.exe", window_title="Demo",
                           process_id=32, elements=[
                               UIElement(automation_id="SaveButton",
                                         control_type="Button", name="Save")
                           ])

    def execute(self, action):
        self.input_calls += 1

    def emergency_release(self):
        pass


class SlowModel:
    def __init__(self):
        self.gate = asyncio.Event()
        self.fail = False
        self.calls = 0

    async def plan(self, objective, observation, scene_summary=None):
        self.calls += 1
        await self.gate.wait()
        if self.fail:
            raise RuntimeError("Strict local JSON validation failed; no actions accepted")
        return Plan(objective=objective, explanation="Review the Save button",
                    actions=[Action(kind="ui.click", automation_id="SaveButton",
                                    expected=Expectation(
                                        automation_id="SaveButton", property="exists"))])

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_plan_start_returns_immediately_and_requires_separate_review(tmp_path):
    desktop, inference = DemoDesktop(), SlowModel()
    app = create_app(token="a" * 36, reasoning_model="local-fixture",
                     desktop=desktop, inference=inference, root=tmp_path)
    transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": "Bearer " + "a" * 36}
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
            created = await api.post("/sessions", headers=headers,
                json={"objective": "Click Save", "executable": "demo.exe"})
            assert created.status_code == 200
            sid = created.json()["id"]
            assert (await api.post(
                f"/sessions/{sid}/plan/start", headers={"Authorization": "Bearer INVALID"}
            )).status_code == 401
            response = await api.post(f"/sessions/{sid}/plan/start", headers=headers)
            assert response.status_code == 202
            assert response.json()["accepted"] is True
            assert response.json()["session_id"] == sid
            # The worker waits for local inference, yet the HTTP control plane
            # continues responding immediately.
            for _ in range(30):
                stage = (await api.get(f"/sessions/{sid}", headers=headers)).json()["state"]
                if stage == "planning":
                    break
                await asyncio.sleep(0.01)
            assert stage == "planning"
            assert (await api.post(f"/sessions/{sid}/execute", headers=headers)).status_code == 409
            assert (await api.post(f"/sessions/{sid}/plan/start", headers=headers)).status_code == 409
            assert desktop.input_calls == 0

            inference.gate.set()
            for _ in range(100):
                result = (await api.get(f"/sessions/{sid}", headers=headers)).json()
                if result["state"] == "waiting_for_user":
                    break
                await asyncio.sleep(0.01)
            assert result["state"] == "waiting_for_user"
            assert result["plan"]["actions"][0]["automation_id"] == "SaveButton"
            assert desktop.input_calls == 0
    finally:
        app.state.agent.memory.close()


@pytest.mark.asyncio
async def test_failed_background_planner_marks_session_failed_with_no_actions(tmp_path):
    desktop, inference = DemoDesktop(), SlowModel()
    inference.fail = True
    app = create_app(token="b" * 36, reasoning_model="local-fixture",
                     desktop=desktop, inference=inference, root=tmp_path)
    headers = {"Authorization": "Bearer " + "b" * 36}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://test") as api:
            sid = (await api.post("/sessions", headers=headers,
                json={"objective": "Click Save", "executable": "demo.exe"})).json()["id"]
            assert (await api.post(f"/sessions/{sid}/plan/start",
                                   headers=headers)).status_code == 202
            inference.gate.set()
            for _ in range(100):
                response = (await api.get(f"/sessions/{sid}", headers=headers)).json()
                if response["state"] == "failed":
                    break
                await asyncio.sleep(0.01)
            assert response["state"] == "failed"
            assert "validation failed" in response["error"]
            assert desktop.input_calls == 0
    finally:
        app.state.agent.memory.close()
