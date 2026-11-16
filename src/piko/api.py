"""Loopback-only bearer authenticated control plane. Not exposed to the LAN."""
from __future__ import annotations

import asyncio
import base64
import binascii
from contextlib import asynccontextmanager
from datetime import datetime
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from piko.contracts import AccessProfile, Grant, Plan, SessionState
from piko.coach import LocalScreenCoach
from piko.memory import LocalMemory
from piko.ollama import OllamaProvider
from piko.orchestrator import Agent
from piko.permissions import PermissionManager
from piko.skills import SkillLibrary
from piko.setup import SetupCoordinator
from piko.teach import TeachRecorder
from piko.windows import WindowsDesktop


class CoachStartRequest(BaseModel):
    executable: str = Field(min_length=4, max_length=100)
    window_handle: int = Field(gt=0)
    seconds: int = Field(default=1800, ge=30, le=3600)
    interval_seconds: float = Field(default=4.0, ge=3, le=30)
    consent: bool = False


class SetupInstallRequest(BaseModel):
    reasoning_model: str = Field(min_length=1, max_length=150)
    vision_model: str | None = Field(default=None, max_length=150)
    confirm_download: bool = False


class CreateSession(BaseModel):
    objective: str = Field(min_length=1, max_length=500)
    executable: str
    target_window_handle: int | None = Field(default=None, ge=1)
    target_process_id: int | None = Field(default=None, ge=1)
    target_process_started_at: float | None = Field(default=None, ge=0)
    allow_activate: bool = False


class GrantRequest(BaseModel):
    executable: str
    profile: AccessProfile = AccessProfile.LIMITED
    session_id: str | None = None


class ModelSelectionRequest(BaseModel):
    reasoning_model: str = Field(min_length=1, max_length=150)
    vision_model: str | None = Field(default=None, max_length=150)


class SkillRequest(BaseModel):
    slug: str
    description: str


class SkillImportRequest(BaseModel):
    archive_base64: str = Field(min_length=1, max_length=1_500_000)


class SkillReviewRequest(BaseModel):
    authorize_foreground_app: bool
    parameters: dict[str, str] = Field(default_factory=dict, max_length=12)


class SkillRevisionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    plan: Plan


class TeachDraftRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    plan: Plan
    confirmed_user_corrections: bool = False


def data_root() -> Path:
    return Path(os.environ.get("PIKO_DATA_DIR") or
                (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Piko"))


def create_app(*, token: str, reasoning_model: str, vision_model: str | None = None,
               desktop=None, inference=None, root: Path | None = None) -> FastAPI:
    if len(token) < 24:
        raise ValueError("Control-plane token must be at least 24 characters")
    store = LocalMemory((root or data_root()) / "piko.db")
    permissions = PermissionManager()
    desktop = desktop or WindowsDesktop()
    inference = inference or OllamaProvider(reasoning_model=reasoning_model, vision_model=vision_model)
    agent = Agent(desktop, inference, store, permissions,
                  vision=inference.interpret if vision_model else None)
    setup = SetupCoordinator(inference, lambda vision: setattr(
        agent, "vision", inference.interpret if vision else None))
    coach = LocalScreenCoach(desktop, inference)
    skills = SkillLibrary((root or data_root()) / "skills")
    teach = TeachRecorder(desktop, (root or data_root()) / "demonstrations")
    running: dict[str, asyncio.Task] = {}
    skill_runs: dict[str, str] = {}

    async def run_and_record(session_id: str):
        result = await agent.run(session_id)
        # Pause is NOT a terminal outcome. Keep the Skill association until
        # resumed execution actually completes/fails/cancels; otherwise history
        # incorrectly records a failure and forgets the resumed session.
        if result.state not in {
            SessionState.COMPLETED, SessionState.FAILED, SessionState.CANCELLED,
        }:
            return result
        skill_slug = skill_runs.pop(session_id, None)
        if skill_slug:
            evidence = store.list_events(session_id)
            start = next((event["timestamp"] for event in evidence
                          if event["type"] == "session.executing"), None)
            finish = next((event["timestamp"] for event in reversed(evidence)
                           if event["type"] == f"session.{result.state.value}"), None)
            wall_ms = None
            if start is not None and finish is not None:
                elapsed = datetime.fromisoformat(finish) - datetime.fromisoformat(start)
                wall_ms = max(0, int(elapsed.total_seconds() * 1000))
            verified_count = sum(event["type"] == "action.verified" for event in evidence)
            # Sanitize evidence: never write action texts, selectors, model
            # plans, sensitive inputs or screenshots into the Skill history.
            skills.record_run(skill_slug, session_id,
                              succeeded=result.state == SessionState.COMPLETED,
                              wall_duration_ms=wall_ms,
                              verified_actions=verified_count)
        return result
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        agent.emergency_stop()
        await coach.stop()
        if teach.active_id is not None:
            await teach.stop()
        await asyncio.gather(*running.values(), return_exceptions=True)
        await inference.close()
        store.close()

    app = FastAPI(title="Piko local control plane", version="0.1.0a0",
                  docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:1420",
       "http://127.0.0.1:1420", "http://tauri.localhost", "tauri://localhost"],
       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    def auth(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not secrets.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(status_code=401, detail="Invalid local control token")

    def find(sid: str):
        if sid not in agent.sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        return agent.sessions[sid]

    @app.get("/health", dependencies=[Depends(auth)])
    async def health():
        return {"status": "running", "platform": os.name,
                "mode": "local", "active_session_count": len(running)}

    @app.get("/models", dependencies=[Depends(auth)])
    async def models():
        try:
            return {"installed": await inference.models(),
                    "reasoning": getattr(inference, "reasoning_model", None),
                    "vision": getattr(inference, "vision_model", None)}
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/coach", dependencies=[Depends(auth)])
    async def coach_status():
        return coach.status()

    @app.post("/coach/start", dependencies=[Depends(auth)])
    async def coach_start(request: CoachStartRequest):
        if teach.active_id is not None:
            raise HTTPException(status_code=409, detail="Stop Teach recording before game capture")
        if not request.consent:
            raise HTTPException(status_code=403, detail="Explicit local capture consent required")
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Stop desktop automation before visual coaching")
        try:
            await coach.start(request.executable, request.window_handle,
                              seconds=request.seconds,
                              interval_seconds=request.interval_seconds)
            return coach.status()
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/coach/stop", dependencies=[Depends(auth)])
    async def coach_stop():
        await coach.stop()
        return coach.status()

    @app.get("/setup", dependencies=[Depends(auth)])
    async def setup_status():
        return setup.status()

    @app.post("/setup/install", dependencies=[Depends(auth)])
    async def setup_install(request: SetupInstallRequest):
        if coach.status()["active"]:
            raise HTTPException(status_code=409, detail="Stop local screen coaching before changing models")
        if not request.confirm_download:
            raise HTTPException(status_code=403, detail="Confirm third-party runtime and model downloads")
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Cannot install models while the agent is running")
        try:
            setup.start(request.reasoning_model, request.vision_model)
            return setup.status()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/models/selection", dependencies=[Depends(auth)])
    async def select_models(request: ModelSelectionRequest):
        if coach.status()["active"]:
            raise HTTPException(status_code=409, detail="Stop local screen coaching before changing models")
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Cannot change models during execution")
        installed = {model["name"] for model in await inference.models()}
        if request.reasoning_model not in installed:
            raise HTTPException(status_code=422, detail="Reasoning model is not installed in Ollama")
        if request.vision_model:
            if request.vision_model not in installed:
                raise HTTPException(status_code=422, detail="Vision model is not installed in Ollama")
            capabilities = await inference.capabilities(request.vision_model)
            if "vision" not in capabilities:
                raise HTTPException(status_code=422, detail="Selected model does not support vision")
        inference.reasoning_model = request.reasoning_model
        inference.vision_model = request.vision_model
        agent.vision = inference.interpret if request.vision_model else None
        return {"reasoning": inference.reasoning_model, "vision": inference.vision_model}

    @app.post("/permissions", dependencies=[Depends(auth)])
    async def create_grant(request: GrantRequest):
        try:
            grant = Grant(**request.model_dump())
            permissions.grant(grant)
            return {"executable": grant.executable, "profile": grant.profile,
                    "session_id": grant.session_id, "temporary": True}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/permissions/{exe}", dependencies=[Depends(auth)])
    async def revoke_grant(exe: str):
        permissions.revoke(exe)
        return {"revoked": exe}

    @app.get("/windows", dependencies=[Depends(auth)])
    async def target_windows(executable: str):
        try:
            if not executable or "/" in executable or "\\" in executable or not executable.lower().endswith(".exe"):
                raise ValueError("Use a single executable basename such as firefox.exe")
            enumerate_windows = getattr(desktop, "list_windows", None)
            if enumerate_windows is None:
                return []
            return await asyncio.to_thread(enumerate_windows, executable)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/sessions", dependencies=[Depends(auth)])
    async def create_session(request: CreateSession):
        try:
            return agent.create(request.objective, request.executable,
                                target_window_handle=request.target_window_handle,
                                target_process_id=request.target_process_id,
                                target_process_started_at=request.target_process_started_at,
                                allow_activate=request.allow_activate)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/sessions/{sid}/plan", dependencies=[Depends(auth)])
    async def plan_session(sid: str):
        find(sid)
        try:
            return await agent.prepare(sid)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/sessions/{sid}/execute", dependencies=[Depends(auth)])
    async def execute_session(sid: str):
        if coach.status()["active"]:
            raise HTTPException(status_code=409, detail="Stop read-only Coach before desktop input")
        session = find(sid)
        if session.state != SessionState.WAITING_FOR_USER:
            raise HTTPException(status_code=409, detail="Approve only a reviewed pending plan")
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Another session currently controls inputs")
        running[sid] = asyncio.create_task(run_and_record(sid))
        return {"accepted": True, "session_id": sid}

    @app.post("/sessions/{sid}/pause", dependencies=[Depends(auth)])
    async def pause_session(sid: str):
        find(sid)
        try:
            agent.pause(sid)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"pause_requested": True}

    @app.post("/sessions/{sid}/resume", dependencies=[Depends(auth)])
    async def resume_session(sid: str):
        if coach.status()["active"]:
            raise HTTPException(status_code=409, detail="Stop read-only Coach before desktop input")
        find(sid)
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Another session owns desktop input")
        try:
            agent.resume(sid)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        running[sid] = asyncio.create_task(run_and_record(sid))
        return {"accepted": True, "session_id": sid}

    @app.get("/sessions/{sid}/observation", dependencies=[Depends(auth)])
    async def session_observation(sid: str):
        session = find(sid)
        try:
            snapshot = await asyncio.to_thread(agent._observation, session, True)
        except (RuntimeError, PermissionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        # Explicit snapshot endpoint only: no auto-capture or persistent image storage.
        payload = snapshot.model_dump(mode="json")
        payload["image_base64"] = snapshot.image_base64
        return payload

    @app.post("/sessions/{sid}/stop", dependencies=[Depends(auth)])
    async def stop_session(sid: str):
        find(sid)
        agent.stop(sid)
        return {"stop_requested": True}

    @app.post("/emergency-stop", dependencies=[Depends(auth)])
    async def emergency_stop():
        agent.emergency_stop()
        return {"stop_requested": True}

    @app.get("/sessions", dependencies=[Depends(auth)])
    async def list_sessions():
        return list(agent.sessions.values())

    @app.get("/sessions/{sid}", dependencies=[Depends(auth)])
    async def get_session(sid: str):
        return find(sid)

    @app.get("/sessions/{sid}/events", dependencies=[Depends(auth)])
    async def get_events(sid: str):
        find(sid)
        return store.list_events(sid)

    @app.get("/skills", dependencies=[Depends(auth)])
    async def get_skills():
        return skills.list_skills()

    @app.post("/skills/import", dependencies=[Depends(auth)])
    async def import_skill(request: SkillImportRequest):
        try:
            payload = base64.b64decode(request.archive_base64, validate=True)
            folder = skills.import_archive(payload)
            return {"name": folder.name, "status": "draft", "verified": False}
        except (ValueError, OSError, binascii.Error) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/skills/{slug}/export", dependencies=[Depends(auth)])
    async def export_skill(slug: str):
        try:
            archive = skills.export_archive(slug)
            return Response(archive, media_type="application/zip",
                            headers={"Content-Disposition":
                                     f'attachment; filename="{slug}.piko-skill.zip"'})
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/skills/{slug}/revisions", dependencies=[Depends(auth)])
    async def skill_revisions(slug: str):
        try:
            return {"revisions": skills.revisions(slug)}
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/skills/{slug}/rollback/{revision}", dependencies=[Depends(auth)])
    async def rollback_skill(slug: str, revision: int):
        try:
            return skills.rollback_draft(slug, revision)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/skills/{slug}/review", dependencies=[Depends(auth)])
    async def review_skill(slug: str, request: SkillReviewRequest):
        if not request.authorize_foreground_app:
            raise HTTPException(status_code=403, detail="Explicit app consent required")
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Desktop inputs currently in use")
        try:
            # Bind only user-entered literal text/expectations. Never allow
            # a Skill parameter to select an executable, UIA target or hotkey.
            executable, plan = skills.prepare_plan(slug, request.parameters)
            session = agent.create(plan.objective, executable)
            permissions.grant(Grant(executable=executable, profile=AccessProfile.LIMITED,
                                    session_id=session.id))
            prepared = await agent.prepare_from_plan(session.id, plan)
            skill_runs[session.id] = slug
            return prepared
        except (ValueError, PermissionError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/skills/{slug}/history", dependencies=[Depends(auth)])
    async def skill_history(slug: str):
        try:
            return skills.history(slug)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/skills/{slug}/revise", dependencies=[Depends(auth)])
    async def revise_skill(slug: str, request: SkillRevisionRequest):
        try:
            return skills.revise_draft(slug, request.description, request.plan)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/sessions/{sid}/save-skill", dependencies=[Depends(auth)])
    async def save_skill(sid: str, request: SkillRequest):
        session = find(sid)
        if not session.plan:
            raise HTTPException(status_code=409, detail="No reviewed plan to save")
        try:
            path = skills.save_draft(request.slug, request.description,
                                     session.app_executable, session.plan)
            return {"saved": path.name, "status": "draft", "verified": False}
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/teach/status", dependencies=[Depends(auth)])
    async def teach_status():
        return {"recording": teach.active_id is not None, "id": teach.active_id}

    @app.post("/teach/start", dependencies=[Depends(auth)])
    async def teach_start(request: GrantRequest, seconds: int = 30):
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Stop active desktop automation before recording")
        try:
            permissions.check_observe(request.executable, request.session_id or "teach")
            identifier = await teach.start(
                request.executable, seconds,
                authorize_capture=lambda: permissions.check_observe(
                    request.executable, request.session_id or "teach"),
            )
            return {"id": identifier, "recording": True}
        except (ValueError, RuntimeError, PermissionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def teach_recording_summary(result: dict) -> dict:
        stopped = [
            event["reason"] for event in result["events"]
            if event.get("type") == "capture.stopped"
        ]
        return {
            "id": result["id"], "frames": result["frames"],
            "recording": False, "limitations": result["limitations"],
            "stopped_reason": stopped[-1] if stopped else None,
        }

    @app.get("/teach/latest", dependencies=[Depends(auth)])
    async def teach_latest():
        try:
            result = teach.get_latest()
            return teach_recording_summary(result)
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/teach/stop", dependencies=[Depends(auth)])
    async def teach_stop():
        try:
            result = await teach.stop()
            return teach_recording_summary(result)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/teach/{identifier}/analysis", dependencies=[Depends(auth)])
    async def teach_analysis(identifier: str):
        try:
            return teach.analyze(identifier)
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/teach/{identifier}/draft", dependencies=[Depends(auth)])
    async def teach_save_corrected_draft(identifier: str, request: TeachDraftRequest):
        if not request.confirmed_user_corrections:
            raise HTTPException(status_code=403, detail="User correction review required")
        try:
            analysis = teach.analyze(identifier)
            # Observations alone are NOT evidence of a demonstration procedure.
            if analysis["input_events"] < 1:
                raise ValueError("No permitted input events to learn from")
            manifest_path = teach.root / identifier / "manifest.json"
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            known = {el["automation_id"]
                     for event in manifest["events"] if event["type"] == "observation"
                     for el in event["data"]["elements"] if el["automation_id"]}
            for action in request.plan.actions:
                if action.automation_id and action.automation_id not in known:
                    raise ValueError("Corrected Skill action has an unobserved UI target")
                if action.expected.automation_id not in known:
                    raise ValueError("Corrected Skill outcome has an unobserved UI target")
            if request.plan.actions[-1].expected.property == "exists":
                raise ValueError("A pre-existing element cannot prove final task success")
            if any(a.expected.value == "REPLACE_WITH_OBSERVED_OUTCOME"
                   for a in request.plan.actions):
                raise ValueError("Enter concrete expected outcomes before saving")
            folder = skills.save_draft(request.slug, request.description, manifest["app"],
                                       request.plan)
            return {"saved": folder.name, "status": "draft", "verified": False,
                    "source_demonstration": identifier}
        except (ValueError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete("/teach/{identifier}", dependencies=[Depends(auth)])
    async def teach_delete(identifier: str):
        teach.delete(identifier)
        return {"deleted": identifier}

    app.state.agent = agent
    app.state.teach = teach
    app.state.permissions = permissions
    return app
