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


def test_refuse_unexpected_template_parameter():
    with pytest.raises(SkillParameterError, match="unexpected"):
        bind_plan(template(), {"name": "Ada", "other": "no"})


def test_refuse_non_string_user_substitution():
    with pytest.raises(SkillParameterError, match="Invalid text value"):
        bind_plan(template(), {"name": 47})


def test_refuse_parameter_longer_than_text_quota():
    with pytest.raises(SkillParameterError, match="Invalid text value"):
        bind_plan(template(), {"name": "x" * 1001})


def test_accept_parameter_at_text_quota_boundary():
    bound = bind_plan(template(), {"name": "x" * 1000})
    assert bound.actions[0].text == "x" * 1000
