"""Action schema regressions: generated plans cannot invent unsafe fields."""

import pytest
from pydantic import ValidationError

from piko.contracts import Action, Expectation


def expected():
    return Expectation(automation_id="Status", property="exists")


def test_refuse_click_without_control_id():
    with pytest.raises(ValidationError):
        Action(kind="ui.click", expected=expected())


def test_refuse_text_action_without_control_id():
    with pytest.raises(ValidationError):
        Action(kind="ui.set_text", text="Ada", expected=expected())


def test_refuse_text_action_without_text():
    with pytest.raises(ValidationError):
        Action(kind="ui.set_text", automation_id="Name", expected=expected())


def test_refuse_empty_hotkey():
    with pytest.raises(ValidationError):
        Action(kind="keyboard.hotkey", expected=expected())


def test_refuse_unbounded_hotkey_chord():
    with pytest.raises(ValidationError):
        Action(kind="keyboard.hotkey", keys=["a", "b", "c", "d"], expected=expected())


def test_refuse_click_with_keyboard_side_effect():
    with pytest.raises(ValidationError):
        Action(kind="ui.click", automation_id="Save", keys=["ctrl", "a"], expected=expected())


def test_refuse_wait_with_text_side_effect():
    with pytest.raises(ValidationError):
        Action(kind="wait.condition", text="unexpected", expected=expected())


def test_refuse_timeout_below_lower_bound():
    with pytest.raises(ValidationError):
        Action(kind="wait.condition", timeout_seconds=0.09, expected=expected())


def test_refuse_timeout_above_upper_bound():
    with pytest.raises(ValidationError):
        Action(kind="wait.condition", timeout_seconds=15.01, expected=expected())


def test_accept_minimum_bounded_wait():
    action = Action(kind="wait.condition", timeout_seconds=0.1, expected=expected())
    assert action.timeout_seconds == 0.1
