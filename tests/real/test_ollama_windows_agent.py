"""Real (not mocked) Ollama -> authorized Agent -> WinForms UIA -> observed state.

Only exercised when explicitly enabled on a controlled interactive Windows
desktop with running Ollama and an installed local reasoning model. Running
this on hosted Windows is not a clean Win10/11 installer acceptance result.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32"
    or os.environ.get("PIKO_GUI_SMOKE") != "1"
    or os.environ.get("PIKO_REAL_OLLAMA") != "1",
    reason="Requires explicit live Ollama and interactive native Windows testbench",
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_real_model_agent_clicks_controlled_winforms_and_verifies_ui(tmp_path):
    from pywinauto import Desktop

    from piko.contracts import AccessProfile, ActionKind, Expectation, Grant, SessionState
    from piko.memory import LocalMemory
    from piko.ollama import OllamaProvider
    from piko.orchestrator import Agent
    from piko.permissions import PermissionManager
    from piko.verification import verify
    from piko.windows import WindowsDesktop

    reasoning = os.environ.get("PIKO_OLLAMA_REASONING_MODEL")
    assert reasoning, "PIKO_OLLAMA_REASONING_MODEL must be an installed Ollama model"

    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(ROOT / "examples/testbench.ps1"),
         "-Title", "Piko Live Ollama Agent Acceptance"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    store = None
    provider = OllamaProvider(reasoning_model=reasoning, timeout=300)
    try:
        window = Desktop(backend="uia").window(title="Piko Live Ollama Agent Acceptance")
        window.wait("visible enabled", timeout=30)
        window.set_focus()

        native = WindowsDesktop()
        initial = native.observe()
        assert initial.process_id == process.pid
        assert initial.window_handle and initial.process_started_at is not None
        assert {"SaveButton", "StatusLabel"} <= {
            element.automation_id for element in initial.elements
        }

        store = LocalMemory(tmp_path / "live-ollama-agent.sqlite")
        permissions = PermissionManager()
        agent = Agent(native, provider, store, permissions)
        objective = (
            "Click the SaveButton exactly once without typing any text. "
            "Verify StatusLabel changes from Waiting to 'Error: enter a name'. "
            "Do not interact with NameInput or any other control."
        )
        session = agent.create(objective, initial.executable)
        permissions.grant(Grant(
            executable=initial.executable, session_id=session.id,
            profile=AccessProfile.LIMITED,
        ))

        # This calls the actual remote-free OllamaProvider.plan and validates
        # model JSON against Piko's strict Plan schema.
        ready = await agent.prepare(session.id)
        assert ready.state == SessionState.WAITING_FOR_USER
        assert ready.plan is not None and len(ready.plan.actions) == 1
        action = ready.plan.actions[0]
        assert action.kind == ActionKind.CLICK and action.automation_id == "SaveButton"
        assert action.expected.automation_id == "StatusLabel"
        assert action.expected.property in {"text_equals", "text_contains"}
        assert action.expected.value == "Error: enter a name"
        assert provider.last_latency_ms is not None and provider.last_latency_ms > 0

        # Planning is not execution; approval is a separate boundary.
        ok, why = verify(Expectation(
            automation_id="StatusLabel", property="text_equals", value="Waiting",
        ), native.observe())
        assert ok, why

        completed = await agent.run(session.id)
        assert completed.state == SessionState.COMPLETED, completed.error
        verified, why = verify(Expectation(
            automation_id="StatusLabel", property="text_equals",
            value="Error: enter a name",
        ), native.observe())
        assert verified, why
        events = store.list_events(session.id)
        assert sum(event["type"] == "action.verified" for event in events) == 1
        assert all(objective not in str(event["payload"]) for event in events)
    finally:
        if store is not None:
            store.close()
        await provider.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
