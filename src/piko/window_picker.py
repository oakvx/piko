"""Explicit, one-click desktop window picker, never a persistent input monitor.

No typed text or screenshots are recorded. The user's next physical left click
selects one already enumerated, visible top-level application window.
"""
from __future__ import annotations

import threading
import time


class WindowClickPicker:
    def __init__(self, desktop, *, listener_factory=None) -> None:
        self.desktop = desktop
        self.listener_factory = listener_factory
        self._lock = threading.Lock()
        self._listener = None
        self._timer = None
        self._state = {"status": "idle", "window": None}
        self._generation = 0

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self, duration: int = 12) -> dict:
        if not 5 <= duration <= 20:
            raise ValueError("Window picking is limited to 5–20 seconds")
        with self._lock:
            if self._state["status"] == "listening":
                raise ValueError("A window selection is already running")
        if self.listener_factory is None:
            from pynput.mouse import Listener
            factory = Listener
        else:
            factory = self.listener_factory
        started = time.monotonic()
        # The initiating button press must not become the picked target.
        ready_at = started + 0.45
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._state = {"status": "listening", "window": None}
            def clicked(x, y, button, pressed):
                name = str(getattr(button, "name", button)).casefold()
                if not pressed or name != "left" or time.monotonic() < ready_at:
                    return
                try:
                    window = self.desktop.window_at(x, y)
                except Exception:
                    return
                if window is None:
                    return
                # Do not pick Piko's own window or infrastructure processes.
                if window["executable"].casefold() in {
                    "piko.exe", "piko-agent.exe", "piko-agent",
                }:
                    return
                with self._lock:
                    if generation != self._generation or self._state["status"] != "listening":
                        return
                    self._state = {"status": "selected", "window": window}
                self._stop_listeners()

            listener = factory(on_click=clicked)
            self._listener = listener
            self._timer = threading.Timer(duration, lambda: self._expire(generation))
            self._timer.daemon = True
        try:
            listener.start()
            self._timer.start()
        except Exception:
            self.cancel()
            raise
        return self.status()

    def _stop_listeners(self) -> None:
        with self._lock:
            listener, timer = self._listener, self._timer
            self._listener = None
            self._timer = None
        if timer is not None:
            timer.cancel()
        if listener is not None:
            listener.stop()

    def _expire(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation or self._state["status"] != "listening":
                return
            self._state = {"status": "expired", "window": None}
        self._stop_listeners()

    def cancel(self) -> dict:
        with self._lock:
            self._generation += 1
            self._state = {"status": "cancelled", "window": None}
        self._stop_listeners()
        return self.status()
