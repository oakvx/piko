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
