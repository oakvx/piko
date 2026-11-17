"""Boundary regressions for independently verifiable model expectations."""

import pytest
from pydantic import ValidationError

from piko.contracts import Expectation


def test_reject_empty_uia_target():
    with pytest.raises(ValidationError):
        Expectation(automation_id="", property="exists")


def test_reject_blank_uia_target_after_normalization():
    with pytest.raises(ValidationError):
        Expectation(automation_id="   ", property="exists")


def test_reject_oversized_uia_target():
    with pytest.raises(ValidationError):
        Expectation(automation_id="S" * 129, property="exists")


def test_reject_unrecognized_verification_property():
    with pytest.raises(ValidationError):
        Expectation(automation_id="Status", property="screen_looks_right")


def test_reject_extra_expectation_attributes():
    with pytest.raises(ValidationError):
        Expectation(automation_id="Status", property="exists", x=101)


def test_reject_missing_text_equals_value():
    with pytest.raises(ValidationError):
        Expectation(automation_id="Status", property="text_equals")


def test_reject_missing_text_contains_value():
    with pytest.raises(ValidationError):
        Expectation(automation_id="Status", property="text_contains")


def test_reject_boolean_window_title_reference():
    with pytest.raises(ValidationError):
        Expectation(automation_id="@window", property="window_title_changed", value=True)


def test_reject_missing_enabled_expectation_flag():
    with pytest.raises(ValidationError):
        Expectation(automation_id="Save", property="enabled")
