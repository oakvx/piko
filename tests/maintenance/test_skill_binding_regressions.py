"""Skill parameters may replace literal text, never selectors or permissions."""

import pytest

from piko.contracts import Action, Expectation, Plan
from piko.skill_parameters import SkillParameterError, bind_plan, parameter_names


def template(text="{{name}}", expectation="{{name}}"):
    return Plan(objective="Write approved text", explanation="Edit a reviewed input", actions=[
        Action(kind="ui.set_text", automation_id="NameInput", text=text,
               expected=Expectation(automation_id="NameInput",
                                    property="text_equals", value=expectation))
    ])


def test_sort_and_deduplicate_template_parameter_names():
    plan = template(text="{{beta}} {{alpha}}", expectation="{{alpha}}")
    assert parameter_names(plan) == ["alpha", "beta"]


def test_leave_plain_text_skill_without_parameters():
    assert parameter_names(template(text="Ada", expectation="Ada")) == []


def test_refuse_missing_required_template_input():
    with pytest.raises(SkillParameterError, match="missing"):
        bind_plan(template(), {})
