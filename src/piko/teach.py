"""Opt-in, time-bounded demonstration recording for an approved foreground app.

Privacy boundary: no actual key contents are retained, and windows exposing UIA
password fields are excluded. Recorded procedural extraction is a separate stage.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from piko.platforms import Desktop


class TeachError(RuntimeError):
    pass


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

    async def start(self, executable: str, seconds: int = 30) -> str:
        if self.active_id is not None:
            raise TeachError("Demonstration already active")
        if not 1 <= seconds <= 300:
            raise TeachError("Demonstration duration must be 1–300 seconds")
        snapshot = await asyncio.to_thread(self.desktop.observe)
        if snapshot.executable.casefold() != executable.casefold():
            raise TeachError("Authorized application must be foreground before recording")
        if any(element.is_password for element in snapshot.elements):
            raise TeachError("Password field detected")
        if executable.casefold() in {"keepass.exe", "bitwarden.exe", "1password.exe"}:
            raise TeachError("Credential managers may not be recorded")
        self.active_id = uuid4().hex
        self._app = executable.casefold()
        self._stop.clear()
        self._events = []
        (self.root / self.active_id).mkdir(mode=0o700)
        self._task = asyncio.create_task(self._record(self.active_id, seconds))
        return self.active_id

    async def _record(self, identifier: str, seconds: int) -> None:
        # Keyboard event listener is intentionally omitted from this foundation:
        # global hooks risk capturing private input in another application.
        # UIA snapshots preserve sanitized text fields within authorized app.
        folder = self.root / identifier
        started = time.monotonic()
        frames = 0
        try:
            while time.monotonic() - started < seconds and not self._stop.is_set():
                try:
                    observation = await asyncio.to_thread(self.desktop.observe, True)
                    if observation.executable.casefold() != self._app:
                        self._events.append({"type": "capture.skipped", "reason": "app_changed"})
                    elif not any(e.is_password for e in observation.elements):
                        import base64
                        (folder / f"frame-{frames:04d}.png").write_bytes(
                            base64.b64decode(observation.image_base64, validate=True))
                        record = observation.model_dump(mode="json", exclude={"image_base64"})
                        self._events.append({"type": "observation", "data": record})
                        frames += 1
                except Exception as exc:
                    self._events.append({"type": "capture.skipped", "reason": type(exc).__name__})
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass
        finally:
            (folder / "manifest.json").write_text(json.dumps({
                "id": identifier, "app": self._app, "frames": frames,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "limitations": ["Keyboard and mouse event replay not recorded in this milestone"],
                "events": self._events,
            }, indent=2), encoding="utf-8")
            self.active_id = None

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

    def delete(self, identifier: str) -> None:
        if not identifier.isalnum() or len(identifier) != 32 or identifier == self.active_id:
            raise TeachError("Invalid or active demonstration identifier")
        folder = self.root / identifier
        if folder.is_symlink():
            raise TeachError("Refusing symlink deletion")
        if folder.exists():
            shutil.rmtree(folder)
