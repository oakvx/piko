"""Validate scoped grant identities, session targets and private observation fields."""

import pytest
from pydantic import ValidationError

from piko.contracts import Grant, Observation, Session


def test_reject_grant_with_forward_slash_path():
    with pytest.raises(ValidationError):
        Grant(executable="folder/demo.exe")


def test_reject_grant_with_backslash_path():
    with pytest.raises(ValidationError):
        Grant(executable=r"folder\demo.exe")


def test_normalize_grant_case_for_authorization():
    assert Grant(executable="DEMO.EXE").executable == "demo.exe"


def test_reject_grant_without_app_identity():
    with pytest.raises(ValidationError):
        Grant(executable="")
