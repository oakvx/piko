import pytest
from pydantic import ValidationError

from piko.contracts import Action, ActionKind, Expectation, Grant, Session, SessionState
from piko.permissions import PermissionDenied, PermissionManager
from piko.state import InvalidTransition, transition
from piko.verification import verify
from piko.contracts import Observation, UIElement


def expectation(selector="status"):
    return Expectation(automation_id=selector, property="text_equals", value="Saved: Ada")


def test_state_machine_rejects_invalid_transition():
    s = Session(objective="test", app_executable="testbench.exe")
    assert transition(s, SessionState.OBSERVING).state == SessionState.OBSERVING
    with pytest.raises(InvalidTransition):
        transition(s, SessionState.COMPLETED)


def test_action_validation_blocks_unbounded_actions():
    with pytest.raises(ValidationError):
        Action(kind="shell.execute", expected=expectation())
    with pytest.raises(ValidationError):
        Action(kind=ActionKind.CLICK, expected=expectation())
    with pytest.raises(ValidationError):
        Action(kind=ActionKind.SET_TEXT, automation_id="name", expected=expectation())
    with pytest.raises(ValidationError):
        Action(kind=ActionKind.CLICK, automation_id="save", expected=expectation(), x=50)
    with pytest.raises(ValidationError):
        Action(kind=ActionKind.CLICK, automation_id="save", expected=expectation(), timeout_seconds=400)


def test_permissions_explicit_grant_and_scope():
    perms = PermissionManager()
    act = Action(kind=ActionKind.CLICK, automation_id="save", expected=expectation())
    with pytest.raises(PermissionDenied):
        perms.check("testbench.exe", "s1", act)
    perms.grant(Grant(executable="TESTBENCH.EXE", session_id="s1"))
    perms.check("testbench.exe", "s1", act)
    with pytest.raises(PermissionDenied):
        perms.check("testbench.exe", "s2", act)
    perms.revoke("testbench.exe")
    with pytest.raises(PermissionDenied):
        perms.check("testbench.exe", "s1", act)


def test_unsafe_hotkey_denied_even_under_full_access():
    perms = PermissionManager()
    perms.grant(Grant(executable="demo.exe", profile="full"))
    action = Action(kind="keyboard.hotkey", keys=["alt", "f4"], expected=expectation())
    with pytest.raises(PermissionDenied):
        perms.check("demo.exe", "any", action)


def test_verification_checks_observed_state():
    ob = Observation(window_title="demo", executable="demo.exe", process_id=4,
        elements=[UIElement(automation_id="status", name="Saved: Ada")])
    assert verify(expectation(), ob)[0]
    assert not verify(Expectation(automation_id="status", property="text_equals", value="Other"), ob)[0]
    assert not verify(Expectation(automation_id="missing", property="exists"), ob)[0]
