"""Ctrl+W is narrowly authorized and tab closure needs observable evidence."""
import pytest

from piko.contracts import Action, Expectation, Grant, Observation
from piko.permissions import PermissionDenied, PermissionManager
from piko.verification import verify


def test_title_changed_verifies_against_fresh_observation():
    expected = Expectation(automation_id="@window", property="window_title_changed",
                           value="Previous tab — Firefox")
    before = Observation(window_title="Previous tab — Firefox", process_id=3,
                         executable="firefox.exe", elements=[])
    after = before.model_copy(update={"window_title": "New tab — Firefox"})
    assert not verify(expected, before)[0]
    assert verify(expected, after)[0]


def test_reviewed_close_tab_hotkey_is_allowed_but_privileged_hotkeys_stay_blocked():
    permissions = PermissionManager()
    permissions.grant(Grant(executable="firefox.exe", session_id="tab-test"))
    expected = Expectation(automation_id="@window", property="window_title_changed",
                           value="Previous tab — Firefox")
    permissions.check("firefox.exe", "tab-test",
                      Action(kind="keyboard.hotkey", keys=["ctrl", "w"], expected=expected))
    with pytest.raises(PermissionDenied):
        permissions.check("firefox.exe", "tab-test",
                          Action(kind="keyboard.hotkey", keys=["alt", "f4"], expected=expected))
    with pytest.raises(PermissionDenied):
        permissions.check("firefox.exe", "other-session",
                          Action(kind="keyboard.hotkey", keys=["ctrl", "w"], expected=expected))
