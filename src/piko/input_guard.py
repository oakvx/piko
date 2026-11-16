"""Small testable keyboard ownership gate.

Only keys injected by Piko are released. Refuse a chord if any of its keys
are already physically pressed by the user; otherwise releasing that key
would interfere with user input. No background typing or global hooks.

A separate chord lock serializes operations while the ownership lock protects
the pressed-key ledger. Target validation deliberately runs WITHOUT holding the
ownership lock: emergency stop can release already-injected keys even when a
native foreground/UIA validation call is hung.
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
        self._chord_lock = threading.Lock()
        self._aborted = threading.Event()
        self._owned: list[int] = []

    def begin_session(self) -> None:
        # Do not re-arm input while an old worker is still inside a hung
        # target check. Returning a refusal is safer than blocking forever.
        if not self._chord_lock.acquire(blocking=False):
            raise InputStopped("A previous keyboard chord is still active")
        try:
            with self._lock:
                if self._owned:
                    raise InputStopped("A previous keyboard chord is not released")
                self._aborted.clear()
        finally:
            self._chord_lock.release()

    def chord(self, keys: tuple[int, ...], check_target: Callable[[], None]) -> None:
        if not keys or len(set(keys)) != len(keys):
            raise ValueError("Invalid keyboard chord")
        with self._chord_lock:
            with self._lock:
                if self._aborted.is_set():
                    raise InputStopped("Emergency stop is active")
                if any(self._physically_down(key) for key in keys):
                    raise InputStopped("Cannot override a key held by the user")
            try:
                for key in keys:
                    if self._aborted.is_set():
                        raise InputStopped("Emergency stop during keyboard action")
                    # May block indefinitely in OS/UIA. Do not hold _lock.
                    check_target()
                    with self._lock:
                        # Recheck under ownership lock, so release_all cannot
                        # race another key-down past an emergency stop.
                        if self._aborted.is_set():
                            raise InputStopped("Emergency stop during target validation")
                        if self._physically_down(key):
                            raise InputStopped("Cannot override a key held by the user")
                        self._inject(key, True)
                        self._owned.append(key)
                if self._aborted.is_set():
                    raise InputStopped("Emergency stop during keyboard action")
            finally:
                with self._lock:
                    self._release_locked()

    def _release_locked(self) -> None:
        while self._owned:
            key = self._owned.pop()
            self._inject(key, False)

    def release_all(self) -> None:
        self._aborted.set()
        # Never wait for an OS/UIA foreground check just to release keys.
        with self._lock:
            self._release_locked()
