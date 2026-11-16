"""Small testable keyboard ownership gate.

Only keys injected by Piko are released. Refuse a chord if any of its keys
are already physically pressed by the user; otherwise releasing that key
would interfere with user input. No background typing or global hooks.
"""
from __future__ import annotations

import threading
from collections.abc import Callable


class InputStopped(RuntimeError):
    pass


class OwnedKeyboard:
    def __init__(
        self,
        inject: Callable[[int, bool], None],
        physically_down: Callable[[int], bool],
    ) -> None:
        self._inject = inject
        self._physically_down = physically_down
        self._lock = threading.RLock()
        self._aborted = threading.Event()
        self._owned: list[int] = []

    def begin_session(self) -> None:
        with self._lock:
            if self._owned:
                raise InputStopped("A previous keyboard chord is not released")
            self._aborted.clear()

    def chord(self, keys: tuple[int, ...], check_target: Callable[[], None]) -> None:
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("Invalid keyboard chord")
        with self._lock:
            if self._aborted.is_set():
                raise InputStopped("Emergency stop is active")
            if any(self._physically_down(key) for key in keys):
                raise InputStopped("Cannot override a key held by the user")
            try:
                for key in keys:
                    if self._aborted.is_set():
                        raise InputStopped("Emergency stop during keyboard action")
                    check_target()
                    self._inject(key, True)
                    self._owned.append(key)
                if self._aborted.is_set():
                    raise InputStopped("Emergency stop during keyboard action")
            finally:
                self._release_locked()

    def _release_locked(self) -> None:
        while self._owned:
            key = self._owned.pop()
            self._inject(key, False)

    def release_all(self) -> None:
        self._aborted.set()
        with self._lock:
            self._release_locked()
