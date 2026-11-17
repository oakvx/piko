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
