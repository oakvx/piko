"""Windows-hosted REAL Ollama vision -> consent-scoped Coach -> readable advice.

Runs only in the dedicated real-model GitHub Action or an explicitly opted-in
interactive Windows test session. This uses a controlled WinForms demo, not a
real game and not an assertion about exclusive-fullscreen compatibility.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32"
    or os.environ.get("PIKO_REAL_OLLAMA") != "1"
    or os.environ.get("PIKO_GUI_SMOKE") != "1",
    reason="Needs real local Ollama vision and interactive Windows UI",
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_local_coach_reads_controlled_winforms_with_actual_vision_model():
    from pywinauto import Desktop

    from piko.coach import LocalScreenCoach
    from piko.ollama import OllamaProvider
    from piko.windows import WindowsDesktop

    vision = os.environ.get("PIKO_OLLAMA_VISION_MODEL")
    assert vision, "Select a real locally installed vision model"
    title = "Piko Private Live Vision Acceptance"
    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(ROOT / "examples/testbench.ps1"), "-Title", title],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    provider = OllamaProvider(reasoning_model="",
                              vision_model=vision, timeout=240)
    coach = None
    try:
        window = Desktop(backend="uia").window(title=title)
        window.wait("visible enabled", timeout=30)
        window.set_focus()
        bridge = WindowsDesktop()
        selected = bridge.observe()
        assert selected.process_id == process.pid
        assert selected.window_handle and selected.process_started_at
        assert bridge.is_window_foreground(selected.window_handle)

        # Prove the native HWND-specific pixel path is actually available,
        # instead of silently considering a skipped vision frame successful.
        screenshot = bridge.observe_window(
            selected.window_handle, selected.executable,
            include_image=True, expected=selected,
            window_pixels_only=True,
        )
        assert screenshot.image_base64, (
            "Native HWND capture unavailable: Coach cannot analyze the screen"
        )

        coach = LocalScreenCoach(bridge, provider)
        await coach.start(selected.executable, selected.window_handle,
                          seconds=600, interval_seconds=4)
        async with asyncio.timeout(200):
            while coach.status()["frames"] < 1:
                state = coach.status()
                if state["stage"] in {"stopped-safely", "expired"}:
                    raise AssertionError(f"Coach terminated: {state['error']}")
                if state["stage"] == "temporarily-unavailable" and state["error"]:
                    raise AssertionError(f"Local vision inference failed: {state['error']}")
                await asyncio.sleep(0.25)
        result = coach.status()
        assert result["stage"] == "watching"
        assert result["observed_at"]
        assert isinstance(result["advice"], str) and result["advice"].strip()
        assert "image_base64" not in result
        assert "screenshot" not in result
        assert "frames" in result and result["frames"] >= 1
        await coach.stop()
        assert coach.status()["active"] is False
        assert coach.status()["stage"] == "stopped"
    finally:
        if coach is not None:
            await coach.stop()
        await provider.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
