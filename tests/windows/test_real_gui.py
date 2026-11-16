"""Opt-in *real* Windows UIA test, not a fake Desktop implementation.

Runs in a controlled foreground WinForms application. The runner must have an
interactive Windows desktop; a service-only/headless runner must fail clearly.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("PIKO_GUI_SMOKE") != "1",
    reason="Requires explicit real Windows GUI smoke-test environment",
)

ROOT = Path(__file__).resolve().parents[2]


def test_real_windows_testbench_uia_actions_and_observed_outcome():
    from pywinauto import Desktop
    from piko.contracts import Action, Expectation
    from piko.verification import verify
    from piko.windows import WindowsDesktop

    script = ROOT / "examples" / "testbench.ps1"
    app = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        window = Desktop(backend="uia").window(title="Piko Testbench")
        window.wait("visible enabled", timeout=30)
        window.set_focus()
        bridge = WindowsDesktop()
        observation = bridge.observe(include_image=False)
        assert observation.window_title == "Piko Testbench"
        assert observation.process_id == app.pid
        assert observation.window_handle is not None
        ids = {e.automation_id for e in observation.elements}
        assert {"NameInput", "SaveButton", "StatusLabel"} <= ids

        set_text = Action(
            kind="ui.set_text", automation_id="NameInput", text="Ada",
            expected=Expectation(automation_id="NameInput",
                                 property="text_equals", value="Ada"),
        )
        click = Action(
            kind="ui.click", automation_id="SaveButton",
            expected=Expectation(automation_id="StatusLabel",
                                 property="text_equals", value="Saved: Ada"),
        )
        bridge.begin_session()
        bridge.execute_observed(set_text, observation)
        observation = bridge.observe()
        assert verify(set_text.expected, observation)[0]
        bridge.execute_observed(click, observation)
        matched = False
        for _ in range(40):
            latest = bridge.observe()
            matched, _ = verify(click.expected, latest)
            if matched:
                break
            time.sleep(0.1)
        assert matched, (
            "Real Windows UI did not display the saved state: "
            + str([(e.automation_id, e.control_type, e.name, e.value)
                   for e in latest.elements if e.automation_id in
                   {"NameInput", "SaveButton", "StatusLabel"}])
        )
        bridge.emergency_release()
    finally:
        app.terminate()
        try:
            app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()
