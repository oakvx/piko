"""Issue #2 acceptance: real Windows foreground change is denied with evidence.

Requires interactive Windows CI and controlled WinForms windows. Both apps run
as distinct processes with the SAME executable basename (powershell.exe).
This is deliberately stricter than the ordinary foreign-executable smoke.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("PIKO_GUI_SMOKE") != "1",
    reason="Real Windows native UIA security test requires interactive CI",
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_real_same_executable_foreground_switch_fails_with_sanitized_evidence(tmp_path):
    from pywinauto import Desktop
    from piko.contracts import Action, Expectation, Grant, Plan, SessionState
    from piko.memory import LocalMemory
    from piko.orchestrator import Agent
    from piko.permissions import PermissionManager
    from piko.verification import verify
    from piko.windows import WindowsDesktop

    class TrustedPlan:
        async def plan(self, objective, observation, scene_summary=None):
            return Plan(
                objective=objective,
                explanation="Controlled button verification",
                actions=[
                    Action(
                        kind="ui.click", automation_id="SaveButton",
                        expected=Expectation(
                            automation_id="StatusLabel",
                            property="text_equals", value="Error: enter a name",
                        ),
                    ),
                ],
            )

    processes = []
    store = LocalMemory(tmp_path / "issue-2-audit.sqlite")

    def launch(title):
        process = subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "examples/testbench.ps1"),
                "-Title", title,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        processes.append(process)
        window = Desktop(backend="uia").window(title=title)
        window.wait("visible enabled", timeout=30)
        window.set_focus()
        return window

    try:
        authorized = launch("Piko Authorized Security Testbench")
        bridge = WindowsDesktop()
        initial = bridge.observe()
        assert initial.window_title == "Piko Authorized Security Testbench"
        assert initial.window_handle
        assert initial.process_id == processes[0].pid
        assert initial.process_started_at is not None

        agent = Agent(bridge, TrustedPlan(), store, PermissionManager())
        session = agent.create("Click the reviewed Save button", initial.executable)
        agent.permissions.grant(Grant(
            executable=initial.executable,
            session_id=session.id,
        ))
        reviewed = await agent.prepare(session.id)
        assert reviewed.state == SessionState.WAITING_FOR_USER

        foreign = launch("Piko Foreign Security Testbench")
        switched = bridge.observe()
        assert switched.executable == initial.executable
        assert switched.window_handle != initial.window_handle
        assert switched.process_id != initial.process_id

        # Neither visible window may receive the authorized click.
        result = await agent.run(session.id)
        assert result.state == SessionState.FAILED
        assert "window instance changed" in (result.error or "")

        # The foreign app remains untouched even though it presents the same
        # valid UIA SaveButton and runs the same executable powershell.exe.
        untouched, _ = verify(Expectation(
            automation_id="StatusLabel",
            property="text_equals", value="Waiting",
        ), bridge.observe())
        assert untouched

        authorized.set_focus()
        still_untouched, _ = verify(Expectation(
            automation_id="StatusLabel",
            property="text_equals", value="Waiting",
        ), bridge.observe())
        assert still_untouched

        events = store.list_events(session.id)
        refusals = [event for event in events if event["type"] == "action.failed"]
        assert len(refusals) == 1
        assert refusals[0]["payload"] == {
            "action": "ui.click", "index": 0,
            "phase": "preflight", "reason": "RuntimeError",
        }
        assert not any(event["type"] in {"action.executed", "action.verified"}
                       for event in events)
        assert all("powershell" not in str(event["payload"]).lower()
                   for event in events)
    finally:
        store.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
