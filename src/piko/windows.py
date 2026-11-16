"""Windows desktop bridge: semantic UIA targeting, screenshot capture, and safe inputs.

Import lazily. Linux can test the orchestration without pretending to run UI automation.
"""
from __future__ import annotations

import base64
import ctypes
import io
import os
import sys
import threading
from ctypes import wintypes

from piko.contracts import Action, ActionKind, Observation, UIElement
from piko.input_guard import OwnedKeyboard


class DesktopUnavailable(RuntimeError):
    pass


class WindowsDesktop:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise DesktopUnavailable("Windows desktop automation requires Windows 10/11")
        try:
            import mss  # noqa: F401
            import psutil  # noqa: F401
            import pywinauto  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise DesktopUnavailable("Install with: pip install -e '.[windows]'") from exc
        # Correct pixel coordinates on per-monitor DPI configurations where supported.
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
        self._keyboard = OwnedKeyboard(
            self._inject_key,
            lambda key: bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000),
        )
        self._input_stopped = threading.Event()
        # COM/UIA calls are not safely interruptible. Never re-arm a new
        # session, or overlap a second native action, while one is in flight.
        # The emergency stop does not acquire this lock and remains responsive.
        self._native_dispatch_lock = threading.Lock()

    @staticmethod
    def _inject_key(key: int, down: bool) -> None:
        # keybd_event is supported on Windows 10/11. Only keys owned by
        # this agent are released; never synthesize a keyup for user-held keys.
        ctypes.windll.user32.keybd_event(key, 0, 0 if down else 0x0002, 0)

    def begin_session(self) -> None:
        if not self._native_dispatch_lock.acquire(blocking=False):
            raise DesktopUnavailable("A previous native UIA action is still running")
        try:
            self._keyboard.begin_session()
            self._input_stopped.clear()
        finally:
            self._native_dispatch_lock.release()

    def _assert_input_not_stopped(self) -> None:
        signal = getattr(self, "_input_stopped", None)
        if signal is not None and signal.is_set():
            raise DesktopUnavailable("Emergency stop is active; refusing native input")

    def _foreground(self) -> tuple[int, int, str, str]:
        import psutil
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            raise DesktopUnavailable("No active desktop window")
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title_buf = ctypes.create_unicode_buffer(1024)
        user32.GetWindowTextW(hwnd, title_buf, 1024)
        try:
            executable = os.path.basename(psutil.Process(pid.value).exe()).casefold()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            raise DesktopUnavailable("Cannot inspect active window process") from exc
        return hwnd, pid.value, executable, title_buf.value

    @staticmethod
    def _process_started_at(pid: int) -> float:
        """Read process creation time, not just PID (which Windows can reuse)."""
        import psutil

        try:
            return float(psutil.Process(pid).create_time())
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            raise DesktopUnavailable("Cannot verify active process identity") from exc

    def list_windows(self, executable: str) -> list[dict]:
        """List *top-level* windows belonging to the exact requested process.

        Never guess among multiple browser windows or confuse subprocesses
        with independent tabs. The caller must authorize the executable.
        """
        import psutil

        requested = os.path.basename(executable).casefold()
        if not requested.endswith(".exe") or requested != executable.casefold():
            raise DesktopUnavailable("Select an executable basename, for example firefox.exe")
        user32 = ctypes.windll.user32
        handles: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def collect(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd) and user32.GetWindow(hwnd, 4) == 0:
                handles.append(int(hwnd))
            return True

        if not user32.EnumWindows(collect, 0):
            raise DesktopUnavailable("Unable to enumerate desktop windows")
        result: list[dict] = []
        for hwnd in handles:
            title = ctypes.create_unicode_buffer(512)
            if not user32.GetWindowTextW(hwnd, title, len(title)) or not title.value.strip():
                continue
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                proc = psutil.Process(pid.value)
                name = os.path.basename(proc.exe()).casefold()
                if name != requested:
                    continue
                started = float(proc.create_time())
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
            result.append({"window_handle": hwnd, "process_id": pid.value,
                           "process_started_at": started, "executable": name,
                           "title": title.value[:240]})
        return result[:40]

    def _assert_window(self, hwnd: int, executable: str,
                       process_id: int | None = None,
                       started_at: float | None = None) -> dict:
        """Revalidate HWND, process and process lifetime without changing focus."""
        user32 = ctypes.windll.user32
        if not hwnd or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            raise DesktopUnavailable("Selected application window is no longer available")
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        import psutil
        try:
            proc = psutil.Process(pid.value)
            actual_name = os.path.basename(proc.exe()).casefold()
            actual_start = float(proc.create_time())
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
            raise DesktopUnavailable("Selected application process cannot be verified") from exc
        if actual_name != executable.casefold() or (process_id is not None and pid.value != process_id):
            raise DesktopUnavailable("Selected window changed process; operation refused")
        if started_at is not None and actual_start != started_at:
            raise DesktopUnavailable("Selected window PID was reused; operation refused")
        title = ctypes.create_unicode_buffer(1024)
        user32.GetWindowTextW(hwnd, title, len(title))
        return {"pid": pid.value, "started": actual_start, "title": title.value,
                "executable": actual_name}

    def observe_window(self, hwnd: int, executable: str,
                       include_image: bool = False,
                       expected: Observation | None = None) -> Observation:
        """Observe authorized window via UIA even while Piko is foreground.

        Pixels are captured only if this exact window is foreground. Never
        pretend a stale/occluded screenshot is a valid fresh observation.
        """
        identity = self._assert_window(
            hwnd, executable,
            expected.process_id if expected is not None else None,
            expected.process_started_at if expected is not None else None,
        )
        foreground = self._foreground()[0] == hwnd
        if include_image and foreground:
            # Existing scoped capture guards both sides of screenshot capture.
            observed = self.observe(include_image=True)
            if observed.window_handle != hwnd or observed.process_id != identity["pid"]:
                raise DesktopUnavailable("Authorized window changed during capture")
            return observed
        elements = self._elements(hwnd)
        refreshed = self._assert_window(
            hwnd, executable, identity["pid"], identity["started"],
        )
        if any(e.is_password for e in elements):
            raise DesktopUnavailable("Sensitive password field detected; observation blocked")
        return Observation(window_title=refreshed["title"], executable=executable.casefold(),
                           process_id=identity["pid"], window_handle=hwnd,
                           process_started_at=identity["started"], elements=elements)

    def activate_window(self, expected: Observation) -> None:
        """Foreground *only* the already reviewed HWND before approved input."""
        self._assert_input_not_stopped()
        if not expected.window_handle:
            raise DesktopUnavailable("No reviewed Windows target to activate")
        self._assert_window(expected.window_handle, expected.executable,
                            expected.process_id, expected.process_started_at)
        if self._foreground()[0] == expected.window_handle:
            return
        ctypes.windll.user32.SetForegroundWindow(expected.window_handle)
        try:
            self._assert_active(expected)
        except DesktopUnavailable as exc:
            raise DesktopUnavailable(
                "Windows did not allow focusing the reviewed application. "
                "Select its window manually and retry; no input was sent."
            ) from exc

    def _elements(self, hwnd: int) -> list[UIElement]:
        from pywinauto import Desktop
        window = Desktop(backend="uia").window(handle=hwnd)
        elements: list[UIElement] = []
        try:
            wrappers = window.descendants()
        except Exception as exc:
            raise DesktopUnavailable(f"Windows UI Automation unavailable ({type(exc).__name__})") from exc
        for el in wrappers[:300]:
            try:
                info = el.element_info
                is_password = bool(getattr(info, "is_password", False))
                automation_id = info.automation_id or (
                    f"name::{info.control_type}::{info.name}" if info.name else "")
                if not automation_id:
                    continue
                value = None
                if not is_password and info.control_type in {"Edit", "Text"}:
                    try:
                        value = el.get_value() if hasattr(el, "get_value") else None
                    except Exception:
                        value = None
                    # Some WinForms Text/Label UIA wrappers expose an empty
                    # ValuePattern even when their visible window text changed.
                    if value is None or value == "":
                        try:
                            value = el.window_text()
                        except Exception:
                            value = None
                try:
                    rect = el.rectangle()
                    bounds = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
                except Exception:
                    bounds = None
                elements.append(UIElement(automation_id=automation_id, name=info.name or "",
                                          control_type=info.control_type or "", value=value,
                                          enabled=el.is_enabled(), is_password=is_password,
                                          bounds=bounds))
            except Exception:
                continue
        return elements

    def observe(self, include_image: bool = False,
                expected: Observation | None = None) -> Observation:
        # A Teach capture must be scoped BEFORE requesting pixels, not merely
        # discarded after accidentally observing a second foreground window.
        if expected is not None:
            self._assert_active(expected)
        hwnd, pid, executable, title = self._foreground()
        if expected is not None:
            self._assert_active(expected)
        started_at = self._process_started_at(pid)
        identity = Observation(window_title=title, executable=executable,
                               process_id=pid, window_handle=hwnd,
                               process_started_at=started_at, elements=[])
        elements = self._elements(hwnd)
        # UIA enumeration can block and the user can switch windows meanwhile.
        self._assert_active(identity)
        if expected is not None:
            self._assert_active(expected)
        image_base64 = None
        capture_bounds = None
        if include_image:
            # Do not capture any window containing UIA password fields.
            if any(el.is_password for el in elements):
                raise DesktopUnavailable("Capture blocked: window contains a password field")
            from PIL import Image
            import mss
            self._assert_active(identity)
            bounds = wintypes.RECT()
            if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(bounds)):
                raise DesktopUnavailable("Could not determine window bounds")
            rect = {"left": bounds.left, "top": bounds.top,
                    "width": bounds.right - bounds.left,
                    "height": bounds.bottom - bounds.top}
            if rect["width"] < 2 or rect["height"] < 2:
                raise DesktopUnavailable("Active window is minimized or inaccessible")
            capture_bounds = (rect["left"], rect["top"], rect["width"], rect["height"])
            with mss.mss() as capture:
                shot = capture.grab(rect)
            # Never return/store pixels if another application came to front
            # during a window-bounds or screenshot operation.
            self._assert_active(identity)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
            out = io.BytesIO()
            image.save(out, format="PNG")
            image_base64 = base64.b64encode(out.getvalue()).decode("ascii")
        self._assert_active(identity)
        if expected is not None:
            self._assert_active(expected)
        return Observation(window_title=title, executable=executable, process_id=pid,
                           window_handle=hwnd, process_started_at=started_at,
                           elements=elements, image_base64=image_base64,
                           capture_bounds=capture_bounds)

    def observe_scoped(self, approved: Observation,
                       include_image: bool = False) -> Observation:
        """Refuse changed foreground identity before acquiring any pixels."""
        if not approved.window_handle:
            raise DesktopUnavailable("Scoped capture requires an authorized HWND")
        return self.observe(include_image=include_image, expected=approved)

    def _target(self, automation_id: str, hwnd: int):
        from pywinauto import Desktop
        controls = Desktop(backend="uia").window(handle=hwnd).descendants()
        matches = []
        for el in controls:
            try:
                info = el.element_info
                identity = info.automation_id or (
                    f"name::{info.control_type}::{info.name}" if info.name else "")
                if identity == automation_id:
                    if bool(getattr(info, "is_password", False)):
                        raise DesktopUnavailable("UIA target is a password control")
                    matches.append(el)
            except DesktopUnavailable:
                raise
            except Exception:
                # Unreadable controls are not accepted as valid targets.
                continue
        if len(matches) != 1:
            raise DesktopUnavailable(f"UIA target not uniquely resolved ({len(matches)} matches)")
        return matches[0]

    def _assert_active(self, expected: Observation) -> int:
        hwnd, pid, executable, _ = self._foreground()
        if (
            not expected.window_handle
            or hwnd != expected.window_handle
            or pid != expected.process_id
            or executable.casefold() != expected.executable.casefold()
        ):
            raise DesktopUnavailable("Foreground window or process changed; refusing input")
        if (expected.process_started_at is not None
                and self._process_started_at(pid) != expected.process_started_at):
            raise DesktopUnavailable("Foreground PID was reused; refusing input")
        return hwnd

    def execute(self, action: Action) -> None:
        # Never let unbound callers dispatch native desktop input.
        raise DesktopUnavailable("A fresh, authorized window observation is required")

    def execute_observed(self, action: Action, expected: Observation) -> None:
        # Refuse concurrent input rather than queue an operation behind a
        # potentially hung UIA call. A cancelled worker can never be replaced
        # until its native dispatch has actually returned.
        if not self._native_dispatch_lock.acquire(blocking=False):
            raise DesktopUnavailable("A previous native UIA action is still running")
        try:
            self._execute_observed_locked(action, expected)
        finally:
            self._native_dispatch_lock.release()

    def _execute_observed_locked(self, action: Action, expected: Observation) -> None:
        self._assert_input_not_stopped()
        hwnd = self._assert_active(expected)
        if any(el.is_password for el in expected.elements):
            raise DesktopUnavailable("Refusing input: password control observed")
        if action.kind in {ActionKind.CLICK, ActionKind.SET_TEXT}:
            target = self._target(action.automation_id, hwnd)
            if not target.is_enabled():
                raise DesktopUnavailable("UIA target is disabled")
            self._assert_active(expected)
            # Target lookup may hang in COM; stop requests must survive until
            # it returns and prevent invoking the now-unwanted action.
            self._assert_input_not_stopped()
            if action.kind == ActionKind.CLICK:
                # UIA Invoke avoids an unbound global pointer click after a
                # foreground switch. Non-invokable controls are refused.
                if not hasattr(target, "invoke"):
                    raise DesktopUnavailable("Target does not expose a safe UIA Invoke pattern")
                # COM capability/properties may themselves block; re-check
                # authorization and cancellation directly before native input.
                self._assert_active(expected)
                self._assert_input_not_stopped()
                target.invoke()
            else:
                if target.element_info.control_type != "Edit":
                    raise DesktopUnavailable("Refusing text input into non-Edit control")
                if not hasattr(target, "set_edit_text"):
                    raise DesktopUnavailable("Target does not expose UIA text input")
                self._assert_active(expected)
                self._assert_input_not_stopped()
                target.set_edit_text(action.text)
        elif action.kind == ActionKind.HOTKEY:
            # PermissionManager checked the exact allowlist before dispatch.
            codes = {"ctrl": 0x11, "tab": 0x09, "escape": 0x1B,
                     "a": 0x41, "c": 0x43, "v": 0x56, "w": 0x57}
            keys = tuple(codes[key.casefold()] for key in action.keys)
            def check_target() -> None:
                self._assert_active(expected)
                self._assert_input_not_stopped()

            self._keyboard.chord(keys, check_target)
        elif action.kind == ActionKind.WAIT:
            return
        else:
            raise DesktopUnavailable(f"Unsupported action {action.kind}")

    def start_teach_events(self, executable: str, window_handle: int,
                           callback) -> callable:
        """Listen only during opt-in recording; never store typed characters.

        Pynput hooks receive OS events, but forward only structural events while
        the *same* authorized HWND/PID is foreground and no password UIA element
        is present. Credentials and key contents are never forwarded.
        """
        from pynput import keyboard, mouse

        hwnd, pid, active_exe, _ = self._foreground()
        if not window_handle or hwnd != window_handle or active_exe != executable.casefold():
            raise DesktopUnavailable("Teach capture requires the approved foreground HWND")
        process_created_at = self._process_started_at(pid)

        def allowed() -> bool:
            try:
                current_hwnd, current_pid, current_exe, _ = self._foreground()
                return (
                    current_hwnd == hwnd and current_pid == pid
                    and current_exe == executable.casefold()
                    and self._process_started_at(pid) == process_created_at
                    and not any(el.is_password for el in self._elements(hwnd))
                )
            except Exception:
                return False

        def on_click(x, y, button, pressed):
            if pressed and allowed():
                callback({"type": "input.mouse_click", "x": int(x), "y": int(y),
                          "button": getattr(button, "name", "unknown")})

        def on_scroll(x, y, dx, dy):
            if allowed():
                callback({"type": "input.mouse_scroll", "x": int(x), "y": int(y),
                          "dx": int(dx), "dy": int(dy)})

        allowed_keys = {
            keyboard.Key.tab: "tab",
            keyboard.Key.enter: "enter",
            keyboard.Key.esc: "escape",
            keyboard.Key.backspace: "backspace",
        }

        def on_press(key):
            # No alphanumeric keypresses, password values or clipboard data.
            label = allowed_keys.get(key)
            if label is not None and allowed():
                callback({"type": "input.special_key", "key": label})

        mouse_listener = mouse.Listener(on_click=on_click, on_scroll=on_scroll)
        keyboard_listener = keyboard.Listener(on_press=on_press)
        mouse_listener.start()
        try:
            keyboard_listener.start()
        except Exception:
            mouse_listener.stop()
            raise

        def stop() -> None:
            mouse_listener.stop()
            keyboard_listener.stop()

        return stop

    def emergency_release(self) -> None:
        # Stop every later dispatch after a hung UIA lookup eventually returns.
        # This cannot interrupt an invocation already inside a native COM call.
        self._input_stopped.set()
        # Never release inputs belonging to another program or the human user.
        self._keyboard.release_all()
