"""Loopback-only bearer authenticated control plane. Not exposed to the LAN."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from piko.contracts import AccessProfile, Grant, Plan, SessionState
from piko.memory import LocalMemory
from piko.ollama import OllamaProvider
from piko.orchestrator import Agent
from piko.permissions import PermissionManager
from piko.skills import SkillLibrary
from piko.teach import TeachRecorder
from piko.windows import WindowsDesktop


class CreateSession(BaseModel):
    objective: str = Field(min_length=1, max_length=500)
    executable: str


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


class SkillReviewRequest(BaseModel):
    authorize_foreground_app: bool


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
    skills = SkillLibrary((root or data_root()) / "skills")
    teach = TeachRecorder(desktop, (root or data_root()) / "demonstrations")
    running: dict[str, asyncio.Task] = {}
    skill_runs: dict[str, str] = {}

    async def run_and_record(session_id: str):
        result = await agent.run(session_id)
        skill_slug = skill_runs.pop(session_id, None)
        if skill_slug:
            # A passing session is evidence, not automatic Skill certification.
            skills.record_run(skill_slug, session_id,
                              succeeded=result.state == SessionState.COMPLETED)
        return result
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        agent.emergency_stop()
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

    @app.post("/models/selection", dependencies=[Depends(auth)])
    async def select_models(request: ModelSelectionRequest):
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

    @app.post("/sessions", dependencies=[Depends(auth)])
    async def create_session(request: CreateSession):
        try:
            return agent.create(request.objective, request.executable)
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

    @app.post("/skills/{slug}/review", dependencies=[Depends(auth)])
    async def review_skill(slug: str, request: SkillReviewRequest):
        if not request.authorize_foreground_app:
            raise HTTPException(status_code=403, detail="Explicit app consent required")
        if any(not task.done() for task in running.values()):
            raise HTTPException(status_code=409, detail="Desktop inputs currently in use")
        try:
            executable, plan = skills.load_plan(slug)
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
            identifier = await teach.start(request.executable, seconds)
            return {"id": identifier, "recording": True}
        except (ValueError, RuntimeError, PermissionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/teach/latest", dependencies=[Depends(auth)])
    async def teach_latest():
        try:
            result = teach.get_latest()
            return {"id": result["id"], "frames": result["frames"],
                    "recording": False, "limitations": result["limitations"]}
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/teach/stop", dependencies=[Depends(auth)])
    async def teach_stop():
        try:
            result = await teach.stop()
            return {"id": result["id"], "frames": result["frames"], "recording": False,
                    "limitations": result["limitations"]}
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
