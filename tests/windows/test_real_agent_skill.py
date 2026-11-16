"""Real Windows Agent + reviewed Skill E2E on a controlled WinForms target.

Not an Ollama inference test: this deliberately uses a deterministic planner,
while *all desktop observations, input dispatch and UIA verification are real*.
A later clean-VM + real Ollama test must still pass before a stable release.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("PIKO_GUI_SMOKE") != "1",
    reason="Requires explicitly enabled interactive Windows GUI automation",
)

ROOT = Path(__file__).resolve().parents[2]


class ControlledPlanner:
    """Trusted deterministic planning fixture; native desktop bridge is real."""

    async def plan(self, objective, observation, scene_summary=None):
        from piko.contracts import Action, Expectation, Plan

        return Plan(
            objective=objective,
            explanation="Enter an authorized name and verify the saved UI state",
            actions=[
                Action(
                    kind="ui.set_text", automation_id="NameInput", text="Ada",
                    expected=Expectation(
                        automation_id="NameInput", property="text_equals", value="Ada",
                    ),
                ),
                Action(
                    kind="ui.click", automation_id="SaveButton",
                    expected=Expectation(
                        automation_id="StatusLabel",
                        property="text_equals", value="Saved: Ada",
                    ),
                ),
            ],
        )


@pytest.mark.asyncio
async def test_live_agent_then_parameterized_skill_restart_and_replay(tmp_path):
    from pywinauto import Desktop

    from piko.contracts import AccessProfile, Action, Expectation, Grant, Plan, SessionState
    from piko.memory import LocalMemory
    from piko.orchestrator import Agent
    from piko.permissions import PermissionManager
    from piko.skills import SkillLibrary
    from piko.verification import verify
    from piko.windows import WindowsDesktop

    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(ROOT / "examples/testbench.ps1"),
         "-Title", "Piko Full Agent Testbench"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    store = None
    try:
        window = Desktop(backend="uia").window(title="Piko Full Agent Testbench")
        window.wait("visible enabled", timeout=30)
        window.set_focus()
        native = WindowsDesktop()
        initial = native.observe()
        assert initial.window_handle and initial.process_id == process.pid
        assert {"NameInput", "SaveButton", "StatusLabel"} <= {
            element.automation_id for element in initial.elements
        }
        executable = initial.executable

        # Phase 1: full Agent state machine with explicit per-session approval.
        store = LocalMemory(tmp_path / "agent.sqlite")
        permissions = PermissionManager()
        agent = Agent(native, ControlledPlanner(), store, permissions)
        session = agent.create("Save Ada in the controlled form", executable)
        permissions.grant(Grant(
            executable=executable, session_id=session.id, profile=AccessProfile.LIMITED,
        ))
        ready = await agent.prepare(session.id)
        assert ready.state == SessionState.WAITING_FOR_USER
        assert ready.plan is not None
        # Planning alone cannot type or click.
        before = native.observe()
        original_input = next(x for x in before.elements if x.automation_id == "NameInput")
        assert original_input.value != "Ada"
        completed = await agent.run(session.id)
        assert completed.state == SessionState.COMPLETED, completed.error
        assert completed.next_action == 2
        fresh = native.observe()
        assert verify(Expectation(
            automation_id="StatusLabel", property="text_equals", value="Saved: Ada",
        ), fresh)[0]
        evidence = store.list_events(session.id)
        assert sum(item["type"] == "action.verified" for item in evidence) == 2
        assert all("Ada" not in str(item["payload"]) for item in evidence)

        # Phase 2: save a user-reviewed, parameterized DRAFT and simulate a
        # complete runtime restart; use a fresh Agent and permission manager.
        template = Plan(
            objective="Save approved person",
            explanation="Use only the approved NameInput and SaveButton targets",
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
                        automation_id="StatusLabel",
                        property="text_equals", value="Saved: {{person}}",
                    ),
                ),
            ],
        )
        library = SkillLibrary(tmp_path / "skills")
        library.save_draft("winforms-name", "Reusable approved WinForms entry",
                           executable, template)
        assert library.list_skills()[0]["status"] == "draft"
        store.close()
        store = LocalMemory(tmp_path / "agent.sqlite")
        reopened = SkillLibrary(tmp_path / "skills")
        app, reviewed_plan = reopened.prepare_plan("winforms-name", {"person": "Bea"})
        assert app == executable
        assert reviewed_plan.actions[0].text == "Bea"

        new_permissions = PermissionManager()
        new_agent = Agent(native, ControlledPlanner(), store, new_permissions)
        denied = new_agent.create("Try without a fresh grant", executable)
        with pytest.raises(PermissionError):
            await new_agent.prepare_from_plan(denied.id, reviewed_plan)
        assert native.observe().window_title == "Piko Full Agent Testbench"
        assert verify(Expectation(
            automation_id="StatusLabel", property="text_equals", value="Saved: Ada",
        ), native.observe())[0]

        review = new_agent.create(reviewed_plan.objective, executable)
        new_permissions.grant(Grant(
            executable=executable, session_id=review.id, profile=AccessProfile.LIMITED,
        ))
        pending = await new_agent.prepare_from_plan(review.id, reviewed_plan)
        assert pending.state == SessionState.WAITING_FOR_USER
        # Review is not authorization to execute; the visible state is unchanged.
        assert verify(Expectation(
            automation_id="StatusLabel", property="text_equals", value="Saved: Ada",
        ), native.observe())[0]
        replayed = await new_agent.run(review.id)
        assert replayed.state == SessionState.COMPLETED, replayed.error
        final = native.observe()
        assert verify(Expectation(
            automation_id="StatusLabel", property="text_equals", value="Saved: Bea",
        ), final)[0]
        reopened.record_run("winforms-name", review.id, succeeded=True)
        assert SkillLibrary(tmp_path / "skills").history("winforms-name")[-1]["completed"]
        assert reopened.list_skills()[0]["status"] == "draft"
        assert all(
            "Bea" not in str(e["payload"])
            for e in store.list_events(review.id)
        )
    finally:
        if store is not None:
            store.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
