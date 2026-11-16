import asyncio

import httpx
import pytest

from piko.api import create_app
from piko.contracts import Observation, UIElement


class DemoDesktop:
    def observe(self, include_image=False):
        return Observation(window_title="demo", process_id=42, executable="demo.exe",
                           elements=[UIElement(automation_id="action")])
    def execute(self, action):
        pass
    def emergency_release(self):
        pass


class DemoInference:
    async def models(self):
        return [{"name": "test-only"}]
    async def close(self):
        pass
    async def plan(self, objective, observation, scene_summary=None):
        from piko.contracts import Action, Expectation, Plan
        return Plan(objective=objective, explanation="test fixture", actions=[Action(
            kind="ui.click", automation_id="action", timeout_seconds=0.1,
            expected=Expectation(automation_id="action", property="exists"))])


@pytest.mark.asyncio
async def test_token_required_and_approval(tmp_path):
    app = create_app(token="a"*36, reasoning_model="fixture", desktop=DemoDesktop(),
                     inference=DemoInference(), root=tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/sessions", json={"objective":"x", "executable":"demo.exe"})).status_code == 401
        auth = {"Authorization":"Bearer " + "a"*36}
        assert (await client.get("/health", headers=auth)).status_code == 200
        response = await client.post("/sessions", headers=auth,
            json={"objective":"perform action", "executable":"demo.exe"})
        assert response.status_code == 200
        sid = response.json()["id"]
        assert (await client.post(f"/sessions/{sid}/plan", headers=auth)).status_code == 409
        await client.post("/permissions", headers=auth,
            json={"executable":"demo.exe", "profile":"limited", "session_id":sid})
        # Prior failed plan is terminal: create a new session.
        response = await client.post("/sessions", headers=auth,
            json={"objective":"perform action", "executable":"demo.exe"})
        sid = response.json()["id"]
        await client.post("/permissions", headers=auth,
            json={"executable":"demo.exe", "profile":"limited", "session_id":sid})
        assert (await client.post(f"/sessions/{sid}/execute", headers=auth)).status_code == 409
        assert (await client.post(f"/sessions/{sid}/plan", headers=auth)).json()["state"] == "waiting_for_user"
        assert (await client.post(f"/sessions/{sid}/execute", headers=auth)).json()["accepted"]
        await asyncio.sleep(0.05)
        assert (await client.get(f"/sessions/{sid}", headers=auth)).json()["state"] == "completed"

@pytest.mark.asyncio
async def test_snapshot_requires_auth_and_scoped_grant(tmp_path):
    class ScreenDesktop(DemoDesktop):
        def observe(self, include_image=False):
            observed = super().observe()
            return observed.model_copy(update={"image_base64": "YQ==" if include_image else None,
                                                "capture_bounds": (10, 20, 100, 80) if include_image else None})

    app = create_app(token="q"*36, reasoning_model="fixture", desktop=ScreenDesktop(),
                     inference=DemoInference(), root=tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        auth = {"Authorization": "Bearer " + "q"*36}
        sid = (await client.post("/sessions", headers=auth,
            json={"objective": "observe", "executable": "demo.exe"})).json()["id"]
        url = f"/sessions/{sid}/observation"
        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers=auth)).status_code == 409
        await client.post("/permissions", headers=auth,
            json={"executable": "demo.exe", "profile": "observe", "session_id": sid})
        captured = await client.get(url, headers=auth)
        assert captured.status_code == 200
        assert captured.json()["image_base64"] == "YQ=="
        assert captured.json()["capture_bounds"] == [10, 20, 100, 80]
        assert (await client.get("/teach/status", headers=auth)).json()["recording"] is False


@pytest.mark.asyncio
async def test_resume_route_must_revalidate_from_next_step(tmp_path):
    from piko.contracts import Action, Expectation, Plan, SessionState
    from piko.memory import LocalMemory
    from piko.orchestrator import Agent
    from piko.permissions import PermissionManager
    from piko.contracts import Grant

    class CountingDesktop(DemoDesktop):
        def __init__(self):
            self.actions = []
        def execute(self, action):
            self.actions.append(action.automation_id)

    desktop = CountingDesktop()
    memory = LocalMemory(tmp_path / "resume.db")
    perms = PermissionManager()
    agent = Agent(desktop, DemoInference(), memory, perms)
    current = agent.create("two actions", "demo.exe")
    perms.grant(Grant(executable="demo.exe", session_id=current.id))
    first = Action(kind="ui.click", automation_id="action", timeout_seconds=0.1,
                   expected=Expectation(automation_id="action", property="exists"))
    # Mark a route as reviewed, and simulate a safe pause checkpoint after step 1.
    current = current.model_copy(update={"state": SessionState.PAUSED, "next_action": 1,
                                         "plan": Plan(objective="two actions", explanation="test",
                                                      actions=[first, first])})
    agent.sessions[current.id] = current
    agent.resume(current.id)
    result = await agent.run(current.id)
    assert result.state == SessionState.COMPLETED
    assert result.next_action == 2
    assert desktop.actions == ["action"]
    memory.close()


def test_paused_session_cancel_is_immediate(tmp_path):
    from piko.contracts import SessionState
    from piko.memory import LocalMemory
    from piko.orchestrator import Agent
    from piko.permissions import PermissionManager
    db = LocalMemory(tmp_path / "stop.db")
    agent = Agent(DemoDesktop(), DemoInference(), db, PermissionManager())
    session = agent.create("x", "demo.exe")
    agent.sessions[session.id] = session.model_copy(update={"state": SessionState.PAUSED})
    agent.stop(session.id)
    assert agent.sessions[session.id].state == SessionState.CANCELLED
    db.close()
