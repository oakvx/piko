"""Native Windows UIA must inspect a selected *background* window, not Piko."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("PIKO_GUI_SMOKE") != "1",
    reason="Real background UIA acceptance requires interactive Windows",
)

ROOT = Path(__file__).resolve().parents[2]


def test_background_window_uia_uses_selected_hwnd_not_current_foreground():
    from pywinauto import Desktop

    from piko.windows import WindowsDesktop

    processes = []

    def launch(title):
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(ROOT / "examples/testbench.ps1"), "-Title", title],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        processes.append(proc)
        win = Desktop(backend="uia").window(title=title)
        win.wait("visible enabled", timeout=30)
        win.set_focus()
        return win

    try:
        authorized = launch("Piko Approved Background UIA")
        bridge = WindowsDesktop()
        approved = bridge.observe()
        assert approved.process_id == processes[0].pid

        foreign = launch("Piko Other Foreground UIA")
        current = bridge.observe()
        assert current.window_title == "Piko Other Foreground UIA"
        assert current.window_handle != approved.window_handle
        assert current.executable == approved.executable

        # The visual task switcher must enumerate *all* normal top-level
        # windows without asking an end user to supply powershell.exe.
        catalog = bridge.list_windows()
        assert any(item["window_handle"] == approved.window_handle and
                   item["process_id"] == approved.process_id for item in catalog)
        assert any(item["window_handle"] == current.window_handle and
                   item["process_started_at"] == current.process_started_at
                   for item in catalog)
        assert all(item.get("display_name") and isinstance(
            item.get("is_foreground"), bool) for item in catalog)
        assert next(item for item in catalog
                    if item["window_handle"] == current.window_handle)["is_foreground"]

        # The real OS hit-testing API recognizes the current foreground window
        # at a visible point. This is a read-only query; no injected click.
        rectangle = foreign.rectangle()
        selected = bridge.window_at(
            (rectangle.left + rectangle.right) // 2,
            (rectangle.top + rectangle.bottom) // 2,
        )
        assert selected is not None
        assert selected["window_handle"] == current.window_handle

        # UIA can inspect the exact approved WinForms window without changing
        # the current foreground and without capturing unrelated pixels.
        found = bridge.list_windows(approved.executable)
        assert any(item["window_handle"] == approved.window_handle and
                   item["process_started_at"] == approved.process_started_at
                   for item in found)
        background = bridge.observe_window(
            approved.window_handle, approved.executable,
            include_image=True, expected=approved,
        )
        assert background.window_handle == approved.window_handle
        assert background.process_id == approved.process_id
        assert background.process_started_at == approved.process_started_at
        # Native HWND-only capture may produce pixels in supported WinForms
        # environments; unavailable/blank capture is a valid UIA fallback.
        # In either case Piko must not capture the foreground foreign process.
        if background.image_base64 is not None:
            assert background.capture_bounds is not None
            assert background.capture_bounds[2] > 1
        assert {"NameInput", "SaveButton", "StatusLabel"} <= {
            item.automation_id for item in background.elements
        }
        assert bridge.observe().window_handle == current.window_handle
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
