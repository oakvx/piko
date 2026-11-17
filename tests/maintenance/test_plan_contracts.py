"""Reject ambiguous, oversized and non-executable plan structures."""

import pytest
from pydantic import ValidationError

from piko.contracts import Action, Expectation, Plan


def click():
    return Action(kind="ui.click", automation_id="Save",
                  expected=Expectation(automation_id="Status", property="exists"))


def make_plan(**overrides):
    data = {"objective": "Save", "explanation": "Use the approved Save button", "actions": [click()]}
    data.update(overrides)
    return Plan(**data)


def test_reject_empty_objective():
    with pytest.raises(ValidationError):
        make_plan(objective="")


def test_reject_whitespace_objective():
    with pytest.raises(ValidationError):
        make_plan(objective="   ")


def test_reject_objective_over_500_characters():
    with pytest.raises(ValidationError):
        make_plan(objective="x" * 501)


def test_reject_empty_explanation():
    with pytest.raises(ValidationError):
        make_plan(explanation="")


def test_reject_whitespace_explanation():
    with pytest.raises(ValidationError):
        make_plan(explanation="   ")


def test_reject_explanation_over_2000_characters():
    with pytest.raises(ValidationError):
        make_plan(explanation="x" * 2001)


def test_reject_plan_without_actions():
    with pytest.raises(ValidationError):
        make_plan(actions=[])


def test_reject_plan_above_action_limit():
    with pytest.raises(ValidationError):
        make_plan(actions=[click() for _ in range(13)])


def test_reject_unreviewed_extra_plan_metadata():
    with pytest.raises(ValidationError):
        make_plan(autorun=True)


def test_accept_exactly_twelve_reviewable_actions():
    plan = make_plan(actions=[click() for _ in range(12)])
    assert len(plan.actions) == 12
