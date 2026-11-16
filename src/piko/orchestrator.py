"""Real observe → plan → authorize → execute → observe → verify control path."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from piko.contracts import ActionKind, Event, Observation, Plan, Session, SessionState
from piko.memory import LocalMemory
from piko.permissions import PermissionManager
from piko.platforms import Desktop
from piko.state import InvalidTransition, transition
from piko.verification import verify

logger = logging.getLogger(__name__)


class Planner(Protocol):
    async def plan(self, objective: str, observation: Observation,
                   scene_summary: str | None = None) -> Plan: ...


class Agent:
    def __init__(self, desktop: Desktop, planner: Planner, memory: LocalMemory,
                 permissions: PermissionManager, *, vision: Callable[[Observation], Awaitable[str]] | None = None) -> None:
        self.desktop = desktop
        self.planner = planner
        self.memory = memory
        self.permissions = permissions
        self.vision = vision
        # Recovered sessions are historical only: LocalMemory marks every
        # nonterminal session failed because plans and grants are not persisted.
        self.sessions: dict[str, Session] = {
            session.id: session for session in self.memory.list_sessions()
        }
        self._active_lock = asyncio.Lock()
        self._cancel: dict[str, asyncio.Event] = {}
        self._pause: dict[str, asyncio.Event] = {}

    def _state(self, session: Session, target: SessionState) -> Session:
        result = transition(session, target)
        self.sessions[result.id] = result
        self.memory.save(result)
        self.memory.write_event(Event(type=f"session.{target.value}", session_id=result.id,
                                      payload={"state": target.value}))
        return result

    def create(self, objective: str, app_executable: str) -> Session:
        if not objective.strip() or not app_executable.lower().endswith(".exe"):
            raise ValueError("Objective and .exe application name are required")
        if "/" in app_executable or "\\" in app_executable:
            raise ValueError("Application name must not include paths")
        session = Session(objective=objective, app_executable=app_executable.casefold())
        self.sessions[session.id] = session
        self.memory.save(session)
        self._cancel[session.id] = asyncio.Event()
        self._pause[session.id] = asyncio.Event()
        return session

    def _observation(self, session: Session, include_image: bool = False) -> Observation:
        # Check consent before screenshot capture, as well as after process
        # identity has been observed. Unauthorized captures must not happen.
        self.permissions.check_observe(session.app_executable, session.id)
        observation = self.desktop.observe(include_image=include_image)
        if observation.executable.casefold() != session.app_executable:
            raise RuntimeError(f"Application changed: expected {session.app_executable}, got {observation.executable}")
        self.permissions.check_observe(observation.executable, session.id)
        if any(e.is_password for e in observation.elements):
            raise RuntimeError("Sensitive password field detected; action blocked")
        return observation

    async def prepare(self, session_id: str) -> Session:
        session = self.sessions[session_id]
        if session.state != SessionState.IDLE:
            raise InvalidTransition("Only idle sessions may be planned")
        session = self._state(session, SessionState.OBSERVING)
        try:
            observation = await asyncio.to_thread(self._observation, session, self.vision is not None)
            session = self._state(session, SessionState.ANALYZING)
            summary = await self.vision(observation) if self.vision else None
            session = self._state(session, SessionState.PLANNING)
            plan = await self.planner.plan(session.objective, observation, summary)
            # Model cannot request UI controls not observed at planning time.
            known = {el.automation_id for el in observation.elements if not el.is_password}
            for action in plan.actions:
                if action.automation_id and action.automation_id not in known:
                    raise ValueError("Proposed plan references a UIA target absent from the current observation")
            session = session.model_copy(update={"plan": plan})
            self.sessions[session.id] = session
            session = self._state(session, SessionState.WAITING_FOR_USER)
            return session
        except Exception as exc:
            session = session.model_copy(update={"error": str(exc)})
            self.sessions[session.id] = session
            self._state(session, SessionState.FAILED)
            raise

    async def prepare_from_plan(self, session_id: str, plan: Plan) -> Session:
        """Review an existing typed Skill plan without trusting it as executable."""
        session = self.sessions[session_id]
        if session.state != SessionState.IDLE:
            raise InvalidTransition("Only new sessions may review a Skill")
        session = self._state(session, SessionState.OBSERVING)
        try:
            observed = await asyncio.to_thread(self._observation, session)
            session = self._state(session, SessionState.ANALYZING)
            # A saved Skill, like LLM output, is untrusted. Check grants and
            # every currently targeted UIA element before user review.
            known = {e.automation_id for e in observed.elements if not e.is_password}
            for action in plan.actions:
                self.permissions.check(session.app_executable, session.id, action)
                if action.automation_id and action.automation_id not in known:
                    raise RuntimeError("Saved Skill target unavailable in the current foreground application")
            session = self._state(session, SessionState.PLANNING)
            session = session.model_copy(update={"plan": plan})
            self.sessions[session.id] = session
            return self._state(session, SessionState.WAITING_FOR_USER)
        except Exception as exc:
            session = session.model_copy(update={"error": str(exc)})
            self.sessions[session.id] = session
            self._state(session, SessionState.FAILED)
            raise

    async def run(self, session_id: str) -> Session:
        session = self.sessions[session_id]
        if session.state not in {SessionState.WAITING_FOR_USER, SessionState.PAUSED} or not session.plan:
            raise InvalidTransition("A reviewed plan or paused session is required")
        if self._active_lock.locked():
            raise RuntimeError("Another agent session owns desktop input")
        async with self._active_lock:
            begin_session = getattr(self.desktop, "begin_session", None)
            if begin_session is not None:
                begin_session()
            session = self._state(session, SessionState.EXECUTING)
            # Only typed action identity/phase enters the persisted evidence
            # ledger. Never write text inputs, screen content or model plans.
            action_context: tuple[str, int, str] | None = None
            try:
                for index in range(session.next_action, len(session.plan.actions)):
                    action = session.plan.actions[index]
                    if self._cancel[session.id].is_set():
                        return self._state(session, SessionState.CANCELLED)
                    if self._pause[session.id].is_set():
                        return self._state(session, SessionState.PAUSED)
                    action_context = (action.kind.value, index, "preflight")
                    before = await asyncio.to_thread(self._observation, session)
                    self.permissions.check(before.executable, session.id, action)
                    # Always observe target again before dispatch; refuse vanished elements.
                    if action.automation_id and action.automation_id not in {
                        el.automation_id for el in before.elements if not el.is_password
                    }:
                        raise RuntimeError(f"UI target disappeared before action {index + 1}")
                    self.memory.write_event(Event(type="action.requested", session_id=session.id,
                                                  payload={"action": action.kind.value, "index": index}))
                    action_context = (action.kind.value, index, "dispatch")
                    # Cancelling wait_for(to_thread(...)) does NOT stop the native
                    # Windows operation. Retain input ownership until the worker
                    # actually exits, including on timeout or coroutine cancellation.
                    guarded_executor = getattr(self.desktop, "execute_observed", None)
                    if guarded_executor is not None:
                        dispatch = asyncio.create_task(
                            asyncio.to_thread(guarded_executor, action, before))
                    else:
                        # Portable test fixture or non-Windows adapter.
                        dispatch = asyncio.create_task(
                            asyncio.to_thread(self.desktop.execute, action))
                    try:
                        await asyncio.wait_for(asyncio.shield(dispatch),
                                               timeout=action.timeout_seconds)
                    except (TimeoutError, asyncio.CancelledError):
                        # A hung UIA call cannot be interrupted safely; waiting is
                        # preferable to releasing the lock while inputs are still active.
                        try:
                            await asyncio.shield(dispatch)
                        except Exception:
                            pass
                        raise
                    self.memory.write_event(Event(type="action.executed", session_id=session.id,
                                                  payload={"action": action.kind.value, "index": index}))
                    session = self._state(session, SessionState.VERIFYING)
                    action_context = (action.kind.value, index, "verification")
                    deadline = asyncio.get_running_loop().time() + action.timeout_seconds
                    ok = False
                    reason = ""
                    while asyncio.get_running_loop().time() < deadline:
                        if self._cancel[session.id].is_set():
                            return self._state(session, SessionState.CANCELLED)
                        after = await asyncio.to_thread(self._observation, session)
                        ok, reason = verify(action.expected, after)
                        if ok:
                            break
                        await asyncio.sleep(0.15)
                    self.memory.write_event(Event(type="verification.completed", session_id=session.id,
                                                  payload={"index": index, "verified": ok}))
                    if not ok:
                        raise RuntimeError(f"Action {index + 1} not verified: {reason}")
                    session = session.model_copy(update={"next_action": index + 1})
                    self.sessions[session.id] = session
                    self.memory.save(session)
                    self.memory.write_event(Event(type="action.verified", session_id=session.id,
                                                  payload={"action": action.kind.value, "index": index}))
                    action_context = None
                    if index + 1 < len(session.plan.actions):
                        session = self._state(session, SessionState.EXECUTING)
                return self._state(session, SessionState.COMPLETED)
            except Exception as exc:
                if action_context is not None:
                    kind, index, phase = action_context
                    self.memory.write_event(Event(type="action.failed", session_id=session.id,
                                                  payload={"action": kind, "index": index,
                                                           "phase": phase, "reason": type(exc).__name__}))
                session = session.model_copy(update={"error": str(exc)})
                self.sessions[session.id] = session
                self.memory.write_event(Event(type="agent.error", session_id=session.id,
                                              payload={"reason": type(exc).__name__}))
                return self._state(session, SessionState.FAILED)
            finally:
                self.desktop.emergency_release()

    def pause(self, session_id: str) -> None:
        if self.sessions[session_id].state not in {SessionState.EXECUTING, SessionState.VERIFYING}:
            raise InvalidTransition("Only executing sessions can be paused")
        self._pause[session_id].set()

    def resume(self, session_id: str) -> None:
        if self.sessions[session_id].state != SessionState.PAUSED:
            raise InvalidTransition("Only paused sessions can resume")
        self._pause[session_id].clear()

    def stop(self, session_id: str) -> None:
        self._cancel[session_id].set()
        self.desktop.emergency_release()
        session = self.sessions[session_id]
        if session.state in {SessionState.IDLE, SessionState.WAITING_FOR_USER, SessionState.PAUSED}:
            self._state(session, SessionState.CANCELLED)

    def emergency_stop(self) -> None:
        for cancel in self._cancel.values():
            cancel.set()
        for session in list(self.sessions.values()):
            if session.state in {SessionState.IDLE, SessionState.WAITING_FOR_USER, SessionState.PAUSED}:
                self._state(session, SessionState.CANCELLED)
        self.desktop.emergency_release()
