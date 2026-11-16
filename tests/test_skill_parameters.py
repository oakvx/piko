"""No parameter may alter selectors, executables, keys or permissions."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from piko.api import create_app
from piko.contracts import Action, Expectation, Observation, Plan, UIElement
from piko.skill_parameters import SkillParameterError, bind_plan, parameter_names
from piko.skills import SkillLibrary


def template() -> Plan:
    return Plan(
        objective="Write a reviewed name",
        explanation="Edit the approved field and verify the observed value",
        actions=[
            Action(kind="ui.set_text", automation_id="NameInput", text="{{person}}",
                   expected=Expectation(automation_id="NameInput",
                                        property="text_equals", value="{{person}}"))
        ],
    )


def test_skill_parameters_declared_and_bound_only_to_text(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    folder = lib.save_draft("name-entry", "Write any reviewed name", "demo.exe", template())
    assert lib.list_skills()[0]["parameters"] == ["person"]
    app, concrete = lib.prepare_plan("name-entry", {"person": "Ada"})
    assert app == "demo.exe"
    assert concrete.actions[0].text == "Ada"
    assert concrete.actions[0].expected.value == "Ada"
    assert concrete.actions[0].automation_id == "NameInput"
    assert lib.load_plan("name-entry")[1].actions[0].text == "{{person}}"
    assert "person" in (folder / "metadata.json").read_text()


def test_skill_parameters_require_exact_user_values():
    plan = template()
    with pytest.raises(SkillParameterError, match="missing"):
        bind_plan(plan, {})
    with pytest.raises(SkillParameterError, match="unexpected"):
        bind_plan(plan, {"person": "Ada", "unsafe": "x"})
    with pytest.raises(SkillParameterError, match="Invalid text"):
        bind_plan(plan, {"person": "x" * 1001})
    with pytest.raises(SkillParameterError):
        bind_plan(plan, {"person": 15})
    # A supplied value containing a second template is literal text.
    bound = bind_plan(plan, {"person": "{{not-evaluated}}"})
    assert bound.actions[0].text == "{{not-evaluated}}"


def test_skill_parameter_cannot_retarget_control_or_insert_hotkeys():
    plan = template()
    plan.actions[0].automation_id = "{{target}}"
    with pytest.raises(SkillParameterError, match="UIA targets"):
        parameter_names(plan)
    plan = template()
    plan.actions[0].expected.automation_id = "{{target}}"
    with pytest.raises(SkillParameterError, match="Verification targets"):
        parameter_names(plan)
    plan = template()
    plan.actions[0].text = "{{bad-name}}"
    with pytest.raises(SkillParameterError, match="Malformed"):
        parameter_names(plan)


def test_skill_revision_tracks_parameter_schema(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    lib.save_draft("name-entry", "Initial", "demo.exe", template())
    updated = template()
    updated.actions[0].text = "{{first}}"
    updated.actions[0].expected.value = "{{first}}"
    lib.revise_draft("name-entry", "Corrected", updated)
    assert lib.list_skills()[0]["parameters"] == ["first"]
    lib.rollback_draft("name-entry", 1)
    assert lib.list_skills()[0]["parameters"] == ["person"]


class Screen:
    def __init__(self):
        self.value = ""

    def observe(self, include_image=False):
        return Observation(
            window_title="Fixture", executable="demo.exe", process_id=78,
            elements=[UIElement(automation_id="NameInput", control_type="Edit",
                                value=self.value)]
        )

    def execute(self, action):
        self.value = action.text

    def emergency_release(self):
        pass


class Inference:
    async def close(self):
        pass


@pytest.mark.asyncio
async def test_api_requires_reviewed_parameters_and_separate_execution(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    lib.save_draft("name-entry", "Fill name", "demo.exe", template())
    desktop = Screen()
    app = create_app(token="a" * 32, reasoning_model="", desktop=desktop,
                     inference=Inference(), root=tmp_path)
    auth = {"Authorization": "Bearer " + "a" * 32}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        endpoint = "/skills/name-entry/review"
        missing = await client.post(endpoint, headers=auth,
                                    json={"authorize_foreground_app": True})
        assert missing.status_code == 409
        assert desktop.value == ""
        reviewed = await client.post(endpoint, headers=auth, json={
            "authorize_foreground_app": True, "parameters": {"person": "Ada"},
        })
        assert reviewed.status_code == 200
        ready = reviewed.json()
        assert ready["state"] == "waiting_for_user"
        assert ready["plan"]["actions"][0]["text"] == "Ada"
        assert desktop.value == ""
        assert (await client.post(f"/sessions/{ready['id']}/execute",
                                  headers=auth)).status_code == 200
        for _ in range(100):
            state = (await client.get(f"/sessions/{ready['id']}", headers=auth)).json()["state"]
            if state in {"completed", "failed"}:
                break
            await asyncio.sleep(0.02)
        assert state == "completed"
        assert desktop.value == "Ada"
        events = (await client.get(f"/sessions/{ready['id']}/events", headers=auth)).json()
        assert all("Ada" not in str(event["payload"]) for event in events)
