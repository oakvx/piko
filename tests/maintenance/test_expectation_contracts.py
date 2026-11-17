"""Boundary regressions for independently verifiable model expectations."""

import pytest
from pydantic import ValidationError

from piko.contracts import Expectation


def test_reject_empty_uia_target():
    with pytest.raises(ValidationError):
        Expectation(automation_id="", property="exists")
