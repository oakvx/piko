"""Windows desktop bridge: semantic UIA targeting, screenshot capture, and safe inputs.

Import lazily. Linux can test the orchestration without pretending to run UI automation.
"""
from __future__ import annotations

import base64
import ctypes
import io
import os
import sys
from ctypes import wintypes

from piko.contracts import Action, ActionKind, Observation, UIElement


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

    def _elements(self, hwnd: int) -> list[UIElement]:
        from pywinauto import Desktop
        window = Desktop(backend="uia").window(handle=hwnd)
        elements: list[UIElement] = []
        try:
            wrappers = window.descendants()
        except Exception as exc:
            raise DesktopUnavailable(f"Windows UI Automation unavailable: {exc}") from exc
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
                        value = el.get_value() if hasattr(el, "get_value") else el.window_text()
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

    def observe(self, include_image: bool = False) -> Observation:
        hwnd, pid, executable, title = self._foreground()
        elements = self._elements(hwnd)
        image_base64 = None
        capture_bounds = None
        if include_image:
            # Do not capture any window containing UIA password fields.
            if any(el.is_password for el in elements):
                raise DesktopUnavailable("Capture blocked: window contains a password field")
            from PIL import Image
            import mss
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
            image = Image.frombytes("RGB", shot.size, shot.rgb)
            out = io.BytesIO()
            image.save(out, format="PNG")
            image_base64 = base64.b64encode(out.getvalue()).decode("ascii")
        return Observation(window_title=title, executable=executable, process_id=pid,
                           elements=elements, image_base64=image_base64,
                           capture_bounds=capture_bounds)

    def _target(self, automation_id: str):
        from pywinauto import Desktop
        hwnd, _, _, _ = self._foreground()
        controls = Desktop(backend="uia").window(handle=hwnd).descendants()
        matches = []
        for el in controls:
            try:
                info = el.element_info
                identity = info.automation_id or (
                    f"name::{info.control_type}::{info.name}" if info.name else "")
                if identity == automation_id and not bool(getattr(info, "is_password", False)):
                    matches.append(el)
            except Exception:
                continue
        if len(matches) != 1:
            raise DesktopUnavailable(f"UIA target {automation_id!r} matched {len(matches)} controls")
        return matches[0]

    def execute(self, action: Action) -> None:
        from pywinauto import keyboard
        if action.kind == ActionKind.CLICK:
            self._target(action.automation_id).click_input()
        elif action.kind == ActionKind.SET_TEXT:
            target = self._target(action.automation_id)
            if target.element_info.control_type != "Edit":
                raise DesktopUnavailable("Refusing text input into non-Edit control")
            if hasattr(target, "set_edit_text"):
                target.set_edit_text(action.text)
            else:
                raise DesktopUnavailable("Target does not expose safe text input")
        elif action.kind == ActionKind.HOTKEY:
            # Whitelist rechecked in PermissionManager before this method is called.
            mapping = {"ctrl": "^", "tab": "{TAB}", "escape": "{ESC}",
                       "a": "a", "c": "c", "v": "v"}
            keyboard.send_keys("".join(mapping[key.casefold()] for key in action.keys))
        elif action.kind == ActionKind.WAIT:
            return  # verification polling is performed by the orchestrator
        else:
            raise DesktopUnavailable(f"Unsupported action {action.kind}")

    def emergency_release(self) -> None:
        # Only atomic input operations in this slice: no held keys/buttons to release.
        # Future continuous-input adapters MUST implement an OS-level release_all here.
        pass
