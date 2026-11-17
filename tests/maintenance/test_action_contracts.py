"""Action schema regressions: generated plans cannot invent unsafe fields."""

import pytest
from pydantic import ValidationError

from piko.contracts import Action, Expectation


def expected():
    return Expectation(automation_id="Status", property="exists")


def test_refuse_click_without_control_id():
    with pytest.raises(ValidationError):
        Action(kind="ui.click", expected=expected())
