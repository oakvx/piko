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
