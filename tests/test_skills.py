import json

import pytest

from piko.contracts import Action, Expectation, Plan
from piko.skills import SkillError, SkillLibrary


def plan():
    return Plan(objective="Fill a form", explanation="Use the name field",
                actions=[Action(kind="ui.set_text", automation_id="NameInput", text="Ada",
                                expected=Expectation(automation_id="NameInput", property="text_equals", value="Ada"))])


def test_skill_roundtrip_is_draft(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    folder = lib.save_draft("form-entry", "Enter a name", "demo.exe", plan())
    assert (folder / "SKILL.md").exists()
    assert "NOT VERIFIED" in (folder / "SKILL.md").read_text()
    assert lib.list_skills()[0]["status"] == "draft"
    app, loaded = lib.load_plan("form-entry")
    assert app == "demo.exe"
    assert loaded.actions[0].text == "Ada"
    with pytest.raises(SkillError):
        lib.save_draft("form-entry", "Overwrite", "demo.exe", plan())


def test_path_traversal_rejected(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    with pytest.raises(SkillError):
        lib.save_draft("../escape", "no", "demo.exe", plan())
    with pytest.raises(SkillError):
        lib.load_plan("../../etc")


def test_skill_import_rejects_invalid_plan(tmp_path):
    lib = SkillLibrary(tmp_path / "skills")
    folder = lib.save_draft("sample", "test", "demo.exe", plan())
    (folder / "plan.json").write_text(json.dumps({"objective":"x", "explanation":"y",
        "actions":[{"kind":"shell.execute", "expected":{"automation_id":"x","property":"exists"}}]}))
    with pytest.raises(ValueError):
        lib.load_plan("sample")
