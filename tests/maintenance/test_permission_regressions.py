"""Independent permission checks must survive mixed case, scope and expiry."""

from datetime import datetime, timedelta, timezone

import pytest

from piko.contracts import Action, Expectation, Grant
from piko.permissions import PermissionDenied, PermissionManager


def action(kind="ui.click", keys=None):
    fields = {"kind": kind, "expected": Expectation(automation_id="Status", property="exists")}
    if kind == "ui.click":
        fields["automation_id"] = "Save"
    if keys is not None:
        fields["keys"] = keys
    return Action(**fields)


def test_deny_observation_without_explicit_grant():
    permissions = PermissionManager()
    with pytest.raises(PermissionDenied, match="No permission grant"):
        permissions.check_observe("demo.exe", "session-1")


def test_deny_execution_without_explicit_grant():
    permissions = PermissionManager()
    with pytest.raises(PermissionDenied):
        permissions.check("demo.exe", "session-1", action())


def test_accept_observation_for_matching_session():
    permissions = PermissionManager()
    permissions.grant(Grant(executable="demo.exe", session_id="session-1"))
    permissions.check_observe("demo.exe", "session-1")


def test_deny_grant_from_different_session():
    permissions = PermissionManager()
    permissions.grant(Grant(executable="demo.exe", session_id="session-1"))
    with pytest.raises(PermissionDenied, match="different session"):
        permissions.check_observe("demo.exe", "session-2")


def test_deny_grant_expired_before_execution():
    permissions = PermissionManager()
    expiry = datetime.now(timezone.utc) - timedelta(seconds=1)
    permissions.grant(Grant(executable="demo.exe", expires_at=expiry))
    with pytest.raises(PermissionDenied, match="expired"):
        permissions.check("demo.exe", "session-1", action())


def test_accept_observation_before_grant_expiry():
    permissions = PermissionManager()
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    permissions.grant(Grant(executable="demo.exe", expires_at=expiry))
    permissions.check_observe("demo.exe", "session-1")


def test_allow_observe_profile_to_read_but_not_click():
    permissions = PermissionManager()
    permissions.grant(Grant(executable="demo.exe", profile="observe"))
    permissions.check_observe("demo.exe", "session-1")
    with pytest.raises(PermissionDenied, match="Observe profile"):
        permissions.check("demo.exe", "session-1", action())


def test_match_grants_without_case_sensitivity():
    permissions = PermissionManager()
    permissions.grant(Grant(executable="DEMO.EXE"))
    permissions.check("Demo.Exe", "session-1", action())


def test_allow_case_normalized_safe_browser_hotkey():
    permissions = PermissionManager()
    permissions.grant(Grant(executable="demo.exe"))
    permissions.check("demo.exe", "session-1", action("keyboard.hotkey", ["CTRL", "W"]))
