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


def test_reject_zero_native_window_handle():
    with pytest.raises(ValidationError):
        Session(objective="Inspect", app_executable="demo.exe", target_window_handle=0)


def test_reject_zero_native_process_id():
    with pytest.raises(ValidationError):
        Session(objective="Inspect", app_executable="demo.exe", target_process_id=0)


def test_reject_negative_process_start_time():
    with pytest.raises(ValidationError):
        Session(objective="Inspect", app_executable="demo.exe", target_process_started_at=-1.0)


def test_reject_extra_session_privileges():
    with pytest.raises(ValidationError):
        Session(objective="Inspect", app_executable="demo.exe", allow_background_stream=True)
