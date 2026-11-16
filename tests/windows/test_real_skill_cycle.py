"""Real Windows Skill lifecycle against a controlled WinForms application.

NOT a mock desktop or model-inference claim. Requires a foreground interactive
Windows session; demonstrates actual UIA input, independent state verification,
the loopback-authenticated API, persisted Skill reloading, and fresh consent
after the local API runtime is reconstructed.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("PIKO_GUI_SMOKE") != "1",
    reason="Requires explicit real Windows GUI smoke-test environment",
)

ROOT = Path(__file__).resolve().parents[2]


class NoInference:
    """Prove that this test reuses the stored Skill without an LLM response."""

    async def close(self):
        pass

    async def plan(self, *_args, **_kwargs):
        raise AssertionError("A reviewed Skill must not replan using an LLM")


async def completed_session(client: httpx.AsyncClient, auth: dict, sid: str) -> None:
    for _ in range(200):
        response = await client.get(f"/sessions/{sid}", headers=auth)
        assert response.status_code == 200
        state = response.json()["state"]
        if state in {"completed", "failed", "cancelled"}:
            assert state == "completed", (
                "Real UIA Skill did not complete: "
                + str(response.json().get("error", "unknown error"))
            )
            return
        await asyncio.sleep(0.1)
    pytest.fail("Timed out awaiting real Windows Skill execution")


@pytest.mark.asyncio
async def test_real_windows_skill_replay_survives_runtime_restart(tmp_path):
    from pywinauto import Desktop

    from piko.api import create_app
    from piko.contracts import Action, Expectation, Plan
    from piko.skills import SkillLibrary
    from piko.verification import verify
    from piko.windows import WindowsDesktop

    app_process = subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "examples/testbench.ps1"),
            "-Title", "Piko Persisted Skill Testbench",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    try:
        window = Desktop(backend="uia").window(title="Piko Persisted Skill Testbench")
        window.wait("visible enabled", timeout=30)
        window.set_focus()
        desktop = WindowsDesktop()
        observed = await asyncio.to_thread(desktop.observe)
        assert observed.window_title == "Piko Persisted Skill Testbench"
        assert observed.process_id == app_process.pid
        assert {"NameInput", "SaveButton", "StatusLabel"} <= {
            item.automation_id for item in observed.elements
        }

        skill_library = SkillLibrary(tmp_path / "skills")
        plan = Plan(
            objective="Save a reviewed person's name",
            explanation="Set the explicit NameInput field then invoke SaveButton",
            actions=[
                Action(
                    kind="ui.set_text", automation_id="NameInput", text="{{person}}",
                    expected=Expectation(
                        automation_id="NameInput", property="text_equals", value="{{person}}",
                    ),
                ),
                Action(
                    kind="ui.click", automation_id="SaveButton",
                    expected=Expectation(
                        automation_id="StatusLabel", property="text_equals",
                        value="Saved: {{person}}",
                    ),
                ),
            ],
        )
        skill_library.save_draft(
            "save-person", "Set a name and verify the saved status",
            "powershell.exe", plan,
        )

        token = "w" * 32
        auth = {"Authorization": f"Bearer {token}"}
        sessions = []
        for name in ("Ada", "Grace"):
            # Reconstruct the API / SQLite connection and create a completely
            # new WindowsDesktop for each replay: no in-memory grant can carry
            # over between these runtime instances.
            backend = WindowsDesktop()
            app = create_app(
                token=token, reasoning_model="", desktop=backend,
                inference=NoInference(), root=tmp_path,
            )
            try:
                window.set_focus()
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    # The second runtime must see the previous completed
                    # session in SQLite, without auto-resuming or reauthorizing.
                    if sessions:
                        old = await client.get(f"/sessions/{sessions[-1]}", headers=auth)
                        assert old.status_code == 200
                        assert old.json()["state"] == "completed"

                    denied = await client.post(
                        "/skills/save-person/review", headers=auth,
                        json={"authorize_foreground_app": False, "parameters": {"person": name}},
                    )
                    assert denied.status_code == 403

                    ready = await client.post(
                        "/skills/save-person/review", headers=auth,
                        json={"authorize_foreground_app": True, "parameters": {"person": name}},
                    )
                    assert ready.status_code == 200, ready.text
                    sid = ready.json()["id"]
                    assert ready.json()["state"] == "waiting_for_user"
                    assert ready.json()["plan"]["actions"][0]["text"] == name
                    sessions.append(sid)

                    launched = await client.post(f"/sessions/{sid}/execute", headers=auth)
                    assert launched.status_code == 200, launched.text
                    await completed_session(client, auth, sid)

                    final = await asyncio.to_thread(backend.observe)
                    saved, reason = verify(
                        Expectation(
                            automation_id="StatusLabel", property="text_equals",
                            value=f"Saved: {name}",
                        ),
                        final,
                    )
                    assert saved, f"Actual WinForms status was not verified: {reason}"

                    events = (await client.get(
                        f"/sessions/{sid}/events", headers=auth
                    )).json()
                    assert len([e for e in events if e["type"] == "action.verified"]) == 2
                    assert name not in str([e["payload"] for e in events])

                    for _ in range(100):
                        history = (await client.get(
                            "/skills/save-person/history", headers=auth
                        )).json()
                        if len(history) == len(sessions):
                            break
                        await asyncio.sleep(0.02)
                    assert len(history) == len(sessions)
                    assert history[-1]["session_id"] == sid
                    assert history[-1]["completed"] is True
            finally:
                app.state.agent.emergency_stop()
                app.state.agent.memory.close()

        assert len(set(sessions)) == 2
        assert skill_library.list_skills()[0]["status"] == "draft"
        assert skill_library.list_skills()[0]["parameters"] == ["person"]
    finally:
        app_process.terminate()
        try:
            app_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app_process.kill()
