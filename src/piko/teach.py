"""Opt-in, time-bounded demonstration recording for an approved foreground app.

Privacy boundary: no actual key contents are retained, and windows exposing UIA
password fields are excluded. Recorded procedural extraction is a separate stage.
"""
from __future__ import annotations

import asyncio
import json
import queue
import re
import shutil
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from piko.contracts import Observation
from piko.platforms import Desktop


class TeachError(RuntimeError):
    pass


# Avoid unbounded memory growth from a noisy OS hook during a 300-second demo.
MAX_PENDING_INPUT_EVENTS = 1024
MAX_RECORDED_INPUT_EVENTS = 4096


class TeachRecorder:
    def __init__(self, desktop: Desktop, root: Path) -> None:
        self.desktop = desktop
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_id: str | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._events: list[dict] = []
        self._app = ""
        self._event_queue: queue.Queue[dict] = queue.Queue(maxsize=MAX_PENDING_INPUT_EVENTS)
        self._recorded_input_events = 0
        self._dropped_input_events = 0
        self._listener_stop = None
        self._event_capture_available = False
        self._authorized: Callable[[], None] | None = None
        self._identity: tuple[int | None, int, float | None] | None = None
        self._approved_window: Observation | None = None

    async def start(self, executable: str, seconds: int = 30,
                    authorize_capture: Callable[[], None] | None = None) -> str:
        if self.active_id is not None:
            raise TeachError("Demonstration already active")
        if not 1 <= seconds <= 300:
            raise TeachError("Demonstration duration must be 1–300 seconds")
        # Recheck the scoped grant before AND after the preflight observation.
        if authorize_capture is not None:
            authorize_capture()
        snapshot = await asyncio.to_thread(self.desktop.observe)
        if authorize_capture is not None:
            authorize_capture()
        if snapshot.executable.casefold() != executable.casefold():
            raise TeachError("Authorized application must be foreground before recording")
        if any(element.is_password for element in snapshot.elements):
            raise TeachError("Password field detected")
        if executable.casefold() in {"keepass.exe", "bitwarden.exe", "1password.exe"}:
            raise TeachError("Credential managers may not be recorded")
        self.active_id = uuid4().hex
        self._app = executable.casefold()
        self._identity = (
            snapshot.window_handle, snapshot.process_id, snapshot.process_started_at,
        )
        self._authorized = authorize_capture
        # Keep only window identity, never the observed app text/controls.
        self._approved_window = Observation(
            window_title="", executable=self._app,
            process_id=snapshot.process_id,
            window_handle=snapshot.window_handle,
            process_started_at=snapshot.process_started_at,
            elements=[],
        )
        self._stop.clear()
        self._events = []
        folder = self.root / self.active_id
        folder.mkdir(mode=0o700)
        start_events = getattr(self.desktop, "start_teach_events", None)
        self._event_capture_available = start_events is not None
        self._event_queue = queue.Queue(maxsize=MAX_PENDING_INPUT_EVENTS)
        self._recorded_input_events = 0
        self._dropped_input_events = 0
        if start_events is not None:
            try:
                self._listener_stop = start_events(
                    self._app, snapshot.window_handle, self._enqueue_event)
            except Exception as exc:
                self.active_id = None
                self._identity = None
                self._authorized = None
                self._approved_window = None
                shutil.rmtree(folder)
                raise TeachError(f"Cannot start scoped Teach input capture: {exc}") from exc
        self._task = asyncio.create_task(self._record(self.active_id, seconds))
        return self.active_id

    def _enqueue_event(self, event: dict) -> None:
        """Accept only structural event metadata; drop injected free-form fields.

        Never persist a callback-provided text/clipboard/password value, even
        if the adapter erroneously passes one. The native Windows hook already
        scopes events to the approved HWND; this is a second privacy boundary.
        """
        if not isinstance(event, dict) or self.active_id is None or self._stop.is_set():
            return
        if self._authorized is not None:
            try:
                self._authorized()
            except (PermissionError, RuntimeError, ValueError):
                # A revoked/expired grant may not generate even input metadata.
                return
        kind = event.get("type")
        try:
            if kind == "input.special_key":
                key = event["key"]
                if key not in {"tab", "enter", "escape", "backspace"}:
                    return
                safe = {"type": kind, "key": key}
            elif kind in {"input.mouse_click", "input.mouse_scroll"}:
                x, y = event["x"], event["y"]
                if (type(x) is not int or type(y) is not int
                        or abs(x) > 1_000_000 or abs(y) > 1_000_000):
                    return
                safe = {"type": kind, "x": x, "y": y}
                if kind == "input.mouse_click":
                    button = event["button"]
                    if button not in {"left", "right", "middle"}:
                        return
                    safe["button"] = button
                else:
                    dx, dy = event["dx"], event["dy"]
                    if type(dx) is not int or type(dy) is not int:
                        return
                    safe.update({"dx": dx, "dy": dy})
            else:
                return
        except (KeyError, TypeError, ValueError):
            return
        safe["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            self._event_queue.put_nowait(safe)
        except queue.Full:
            self._dropped_input_events += 1

    def _drain_events(self) -> None:
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            if self._recorded_input_events >= MAX_RECORDED_INPUT_EVENTS:
                self._dropped_input_events += 1
                continue
            self._recorded_input_events += 1
            self._events.append(event)

    async def _record(self, identifier: str, seconds: int) -> None:
        """Write only frames from the *same* consented process/window lifetime."""
        folder = self.root / identifier
        started = time.monotonic()
        frames = 0
        try:
            while time.monotonic() - started < seconds and not self._stop.is_set():
                try:
                    if self._authorized is not None:
                        self._authorized()
                    native_scoped = getattr(self.desktop, "observe_scoped", None)
                    if native_scoped is not None and self._approved_window is not None:
                        observation = await asyncio.to_thread(
                            native_scoped, self._approved_window, True)
                    else:
                        # A synthetic/portable Desktop adapter may not expose
                        # scoped capture; recheck identity before saving below.
                        observation = await asyncio.to_thread(self.desktop.observe, True)
                    if self._authorized is not None:
                        self._authorized()
                    identity = (
                        observation.window_handle, observation.process_id,
                        observation.process_started_at,
                    )
                    if (observation.executable.casefold() != self._app
                            or identity != self._identity):
                        # Same executable does not mean same authorized window.
                        # Discard the returned screenshot without writing it.
                        self._events.append({
                            "type": "capture.stopped", "reason": "window_changed",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        self._stop.set()
                        break
                    if any(el.is_password for el in observation.elements):
                        self._events.append({
                            "type": "capture.stopped", "reason": "password_field",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        self._stop.set()
                        break
                    import base64
                    frame_file = f"frame-{frames:04d}.png"
                    (folder / frame_file).write_bytes(
                        base64.b64decode(observation.image_base64, validate=True))
                    record = observation.model_dump(
                        mode="json", exclude={"image_base64"})
                    # Exact file link and completed-capture time connect frames,
                    # UIA metadata and native input events on one UTC timeline.
                    record["frame_index"] = frames
                    record["frame_file"] = frame_file
                    record["captured_at"] = datetime.now(timezone.utc).isoformat()
                    record["window_title"] = ""
                    for element in record["elements"]:
                        element["value"] = None
                        # UIA names and fallback ids can include user secrets.
                        element["name"] = ""
                        if element["automation_id"].startswith("name::"):
                            element["automation_id"] = ""
                    self._events.append({"type": "observation", "data": record})
                    frames += 1
                except PermissionError:
                    # Revocation/expiry ends recording instead of repeatedly
                    # trying to capture an application without a valid grant.
                    self._events.append({
                        "type": "capture.stopped", "reason": "authorization_lost",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    self._stop.set()
                    break
                except Exception as exc:
                    self._events.append({
                        "type": "capture.skipped", "reason": type(exc).__name__,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                self._drain_events()
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        finally:
            if self._listener_stop is not None:
                self._listener_stop()
                self._listener_stop = None
            self._drain_events()
            self._events.sort(key=lambda e: (
                e.get("timestamp") or e.get("data", {}).get("captured_at")
                or e.get("data", {}).get("timestamp") or ""
            ))
            (folder / "manifest.json").write_text(json.dumps({
                "id": identifier, "app": self._app, "frames": frames,
                "dropped_input_events": self._dropped_input_events,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "limitations": (
                    ["Input-event recorder unavailable on this desktop adapter"]
                    if not self._event_capture_available else
                    ["Raw typed characters are intentionally excluded; all inferred steps need review"]
                ),
                "events": self._events,
            }, indent=2), encoding="utf-8")
            self.active_id = None
            self._identity = None
            self._authorized = None
            self._approved_window = None

    async def stop(self) -> dict:
        if self._task is None:
            raise TeachError("No recording has been started")
        self._stop.set()
        await self._task
        self._task = None
        return self.get_latest()

    def get_latest(self) -> dict:
        manifests = sorted(self.root.glob("*/manifest.json"), key=lambda x: x.stat().st_mtime,
                           reverse=True)
        if not manifests:
            raise TeachError("No demonstrations recorded")
        return json.loads(manifests[0].read_text(encoding="utf-8"))

    def analyze(self, identifier: str) -> dict:
        """Conservative temporal grounding, *not* automatic Skill certification."""
        if not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise TeachError("Invalid demonstration identifier")
        manifest_path = self.root / identifier / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise TeachError("Demonstration is unavailable or recording is still active")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        observations = [event["data"] for event in manifest["events"]
                        if event["type"] == "observation"]
        clicks = [event for event in manifest["events"]
                  if event["type"] == "input.mouse_click" and event.get("button") == "left"]
        steps = []
        for click in clicks[:12]:
            candidates = []
            # Use only a screenshot observation taken BEFORE the event. Never
            # guess an element on a changed or unobserved application.
            earlier = [o for o in observations
                       if o.get("captured_at", o["timestamp"]) <= click["timestamp"]
                       and o["executable"] == manifest["app"]]
            if earlier:
                observed = earlier[-1]
                for element in observed["elements"]:
                    bounds = element.get("bounds")
                    if (element.get("automation_id")
                            and element.get("control_type") in {"Button", "CheckBox", "RadioButton"}
                            and bounds and bounds[0] <= click["x"] <= bounds[2]
                            and bounds[1] <= click["y"] <= bounds[3]):
                        area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
                        candidates.append((area, element["automation_id"]))
            candidates.sort()
            target = candidates[0][1] if len(candidates) == 1 else None
            steps.append({
                "kind": "ui.click",
                "automation_id": target,
                "confidence": "tentative" if target else "unresolved",
                "requires_expected_outcome": True,
            })
        return {
            "id": identifier,
            "frames": manifest["frames"],
            "input_events": len([e for e in manifest["events"] if e["type"].startswith("input.")]),
            "steps": steps,
            "uncertainties": [
                "Click targeting is geometric and tentative; review UIA selectors",
                "Expected outcomes, parameters and task goal require user correction",
                "No Skill is verified by this analysis",
            ],
            "status": "needs_review",
        }

    def delete(self, identifier: str) -> None:
        if not identifier.isalnum() or len(identifier) != 32 or identifier == self.active_id:
            raise TeachError("Invalid or active demonstration identifier")
        folder = self.root / identifier
        if folder.is_symlink():
            raise TeachError("Refusing symlink deletion")
        if folder.exists():
            shutil.rmtree(folder)
