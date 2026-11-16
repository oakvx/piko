"""Guarded Skill reuse, history and revision regression tests."""
import asyncio
import base64
import io
import json
import zipfile

import httpx
import pytest

from piko.api import create_app
from piko.contracts import Action, Expectation, Observation, Plan, SessionState, UIElement
from piko.skills import SkillError, SkillLibrary


def sample_plan():
    return Plan(
        objective="Click save",
        explanation="Press a controlled UIA button and verify its state",
        actions=[Action(
            kind="ui.click",
            automation_id="Save",
            expected=Expectation(automation_id="Save", property="exists"),
        )],
    )


class Screen:
    def __init__(self):
        self.executions = 0
        self.application = "demo.exe"
    def observe(self, include_image=False):
        return Observation(
            window_title="Demo", process_id=21, executable=self.application,
            elements=[UIElement(automation_id="Save", control_type="Button")],
        )
    def execute(self, action):
        self.executions += 1
    def emergency_release(self):
        pass


class Inference:
    async def close(self): pass
    async def models(self): return []
    async def plan(self, *args): raise AssertionError("Existing Skill must not replan through LLM")


@pytest.mark.asyncio
async def test_skill_review_rechecks_consent_and_user_execution(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    lib.save_draft("save-demo", "Click the save button", "demo.exe", sample_plan())
    desktop = Screen()
    app = create_app(token="x"*32, reasoning_model="", desktop=desktop,
                     inference=Inference(), root=tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        url = "/skills/save-demo/review"
        auth = {"Authorization": "Bearer " + "x"*32}
        assert (await client.post(url, json={"authorize_foreground_app": True})).status_code == 401
        assert (await client.post(url, headers=auth,
                json={"authorize_foreground_app": False})).status_code == 403
        assert desktop.executions == 0
        ready = await client.post(url, headers=auth, json={"authorize_foreground_app": True})
        assert ready.status_code == 200
        sid = ready.json()["id"]
        assert ready.json()["state"] == "waiting_for_user"
        assert desktop.executions == 0
        assert (await client.post(f"/sessions/{sid}/execute", headers=auth)).status_code == 200
        for _ in range(60):
            if (await client.get(f"/sessions/{sid}", headers=auth)).json()["state"] == "completed":
                break
            await asyncio.sleep(0.02)
        assert desktop.executions == 1
        history = await client.get("/skills/save-demo/history", headers=auth)
        assert history.status_code == 200
        assert history.json()[-1]["completed"] is True
    assert lib.list_skills()[0]["status"] == "draft"


@pytest.mark.asyncio
async def test_skill_replay_rejects_switched_application(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    lib.save_draft("save-demo", "Click save", "demo.exe", sample_plan())
    desktop = Screen()
    desktop.application = "other.exe"
    app = create_app(token="x"*32, reasoning_model="", desktop=desktop,
                     inference=Inference(), root=tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        auth = {"Authorization": "Bearer " + "x"*32}
        resp = await client.post("/skills/save-demo/review", headers=auth,
                                 json={"authorize_foreground_app": True})
        assert resp.status_code == 409
        assert desktop.executions == 0


def test_skill_revision_archives_and_refuses_overwrite_of_verified(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    folder = lib.save_draft("save-demo", "Initial", "demo.exe", sample_plan())
    revised = lib.revise_draft("save-demo", "Corrected", sample_plan())
    assert revised["revision"] == 2
    assert (folder / "revisions/revision-1/plan.json").is_file()
    assert "Corrected" in (folder / "SKILL.md").read_text()
    assert "Corrected" in lib.list_skills()[0]["description"]
    metadata = folder / "metadata.json"
    record = json.loads(metadata.read_text())
    record["status"] = "verified"
    metadata.write_text(json.dumps(record))
    with pytest.raises(SkillError, match="verified"):
        lib.revise_draft("save-demo", "Malicious overwrite", sample_plan())


def test_skill_export_import_is_always_draft_and_rejects_extensions(tmp_path):
    source = SkillLibrary(tmp_path / "source")
    source.save_draft("save-demo", "Click save", "demo.exe", sample_plan())
    archive = source.export_archive("save-demo")
    destination = SkillLibrary(tmp_path / "destination")
    imported = destination.import_archive(archive)
    assert imported.name == "save-demo"
    assert destination.list_skills()[0]["status"] == "draft"
    with pytest.raises(SkillError):
        destination.import_archive(archive)
    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, "w") as zip_file:
        zip_file.writestr("metadata.json", json.dumps({
            "name": "unsafe", "description": "bad", "executable": "demo.exe",
            "status": "verified",
        }))
        zip_file.writestr("plan.json", sample_plan().model_dump_json())
        zip_file.writestr("powershell.exe", "untrusted")
    with pytest.raises(SkillError, match="Unexpected"):
        destination.import_archive(malicious.getvalue())


def test_skill_rollback_is_new_revision_and_preserves_original(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    folder = lib.save_draft("save-demo", "Original description", "demo.exe", sample_plan())
    lib.revise_draft("save-demo", "Second version", sample_plan())
    assert lib.revisions("save-demo") == [1]
    rolled = lib.rollback_draft("save-demo", 1)
    assert rolled["revision"] == 3
    assert rolled["description"] == "Original description"
    assert lib.revisions("save-demo") == [1, 2]
    assert (folder / "revisions/revision-2/metadata.json").exists()


@pytest.mark.asyncio
async def test_skill_archive_api_requires_auth_and_forces_draft(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    lib.save_draft("saved", "Before export", "demo.exe", sample_plan())
    app = create_app(token="x"*32, reasoning_model="", desktop=Screen(),
                     inference=Inference(), root=tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        auth = {"Authorization": "Bearer " + "x"*32}
        assert (await client.get("/skills/saved/export")).status_code == 401
        exported = await client.get("/skills/saved/export", headers=auth)
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/zip"
        archive = exported.content
        with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
            assert set(zip_file.namelist()) == {"metadata.json", "plan.json"}
        # Import a differently named but otherwise identical controlled archive.
        with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
            metadata = json.loads(zip_file.read("metadata.json"))
            plan = zip_file.read("plan.json")
        metadata["name"] = "imported"
        metadata["status"] = "verified"
        modified = io.BytesIO()
        with zipfile.ZipFile(modified, "w") as zip_file:
            zip_file.writestr("metadata.json", json.dumps(metadata))
            zip_file.writestr("plan.json", plan)
        response = await client.post("/skills/import", headers=auth,
            json={"archive_base64": base64.b64encode(modified.getvalue()).decode()})
        assert response.status_code == 200
        assert response.json()["verified"] is False
        assert len((await client.get("/skills", headers=auth)).json()) == 2


@pytest.mark.asyncio
async def test_skill_pause_resume_records_one_terminal_run_with_metrics(tmp_path):
    """Pause is not failure; resumed replay retains its Skill history binding."""
    lib = SkillLibrary(tmp_path / "skills")
    lib.save_draft("save-demo", "Reviewed save", "demo.exe", sample_plan())
    app = create_app(token="p" * 32, reasoning_model="", desktop=Screen(),
                     inference=Inference(), root=tmp_path)
    agent = app.state.agent
    calls = []

    async def deterministic_paused_then_completed(sid):
        calls.append(sid)
        running = agent._state(agent.sessions[sid], SessionState.EXECUTING)
        if len(calls) == 1:
            return agent._state(running, SessionState.PAUSED)
        verifying = agent._state(running, SessionState.VERIFYING)
        return agent._state(verifying, SessionState.COMPLETED)

    agent.run = deterministic_paused_then_completed
    auth = {"Authorization": "Bearer " + "p" * 32}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        reviewed = await client.post("/skills/save-demo/review", headers=auth,
                                    json={"authorize_foreground_app": True})
        assert reviewed.status_code == 200, reviewed.text
        sid = reviewed.json()["id"]
        assert (await client.post(f"/sessions/{sid}/execute",
                                  headers=auth)).status_code == 200
        for _ in range(100):
            state = (await client.get(f"/sessions/{sid}", headers=auth)).json()["state"]
            if state == "paused":
                break
            await asyncio.sleep(0.02)
        assert state == "paused"
        assert (await client.get("/skills/save-demo/history", headers=auth)).json() == []
        # Wait for the first worker to return before starting a fresh run.
        await asyncio.sleep(0.05)
        resumed = await client.post(f"/sessions/{sid}/resume", headers=auth)
        assert resumed.status_code == 200, resumed.text
        for _ in range(100):
            history = (await client.get("/skills/save-demo/history",
                                        headers=auth)).json()
            if len(history) == 1:
                break
            await asyncio.sleep(0.02)
        assert len(history) == 1
        record = history[0]
        assert record["session_id"] == sid
        assert record["completed"] is True
        assert record["verified_actions"] == 0
        assert isinstance(record["wall_duration_ms"], int)
        assert record["wall_duration_ms"] >= 0
        assert calls == [sid, sid]
        assert lib.list_skills()[0]["status"] == "draft"


def test_skill_history_refuses_invalid_performance_fields(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    lib.save_draft("save-demo", "Reviewed save", "demo.exe", sample_plan())
    with pytest.raises(SkillError, match="wall duration"):
        lib.record_run("save-demo", "session", True, wall_duration_ms=-5)
    with pytest.raises(SkillError, match="verified action"):
        lib.record_run("save-demo", "session", True, verified_actions=True)
    assert lib.history("save-demo") == []
