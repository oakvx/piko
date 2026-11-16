"""Negative authorization and input ownership tests runnable off Windows."""
import pytest

from piko.contracts import Action, Expectation, Observation, UIElement
from piko.input_guard import InputStopped, OwnedKeyboard
from piko.windows import DesktopUnavailable, WindowsDesktop


def observation(hwnd=101, pid=24, executable="demo.exe"):
    return Observation(
        window_title="Fixture",
        window_handle=hwnd,
        process_id=pid,
        executable=executable,
        elements=[UIElement(automation_id="Save", control_type="Button")],
    )


def click():
    return Action(kind="ui.click", automation_id="Save",
                  expected=Expectation(automation_id="Save", property="exists"))


def test_windows_bridge_rejects_foreground_switch_before_dispatch():
    bridge = object.__new__(WindowsDesktop)
    bridge._foreground = lambda: (202, 25, "evil.exe", "Other")
    bridge._target = lambda *_args: pytest.fail("Must not resolve a foreign UIA target")
    with pytest.raises(DesktopUnavailable, match="changed"):
        bridge.execute_observed(click(), observation())


def test_windows_bridge_requires_observed_hwnd():
    bridge = object.__new__(WindowsDesktop)
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    with pytest.raises(DesktopUnavailable):
        bridge.execute_observed(click(), observation(hwnd=None))


def test_windows_bridge_uses_pinned_hwnd_and_uia_invoke():
    bridge = object.__new__(WindowsDesktop)
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    called = []
    class Button:
        def is_enabled(self): return True
        def invoke(self): called.append("invoked")
    bridge._target = lambda automation_id, hwnd: (
        called.append((automation_id, hwnd)) or Button())
    bridge.execute_observed(click(), observation())
    assert called == [("Save", 101), "invoked"]


def test_windows_bridge_denies_unbound_execute():
    bridge = object.__new__(WindowsDesktop)
    with pytest.raises(DesktopUnavailable, match="authorized"):
        bridge.execute(click())


def test_owned_keyboard_chord_releases_only_its_keys():
    sent = []
    guard = OwnedKeyboard(lambda key, pressed: sent.append((key, pressed)),
                          lambda key: False)
    guard.begin_session()
    guard.chord((0x11, 0x41), lambda: None)
    assert sent == [(0x11, True), (0x41, True), (0x41, False), (0x11, False)]


def test_owned_keyboard_refuses_keys_held_by_user_without_injecting():
    sent = []
    guard = OwnedKeyboard(lambda key, pressed: sent.append((key, pressed)),
                          lambda key: key == 0x11)
    guard.begin_session()
    with pytest.raises(InputStopped, match="user"):
        guard.chord((0x11, 0x41), lambda: None)
    assert sent == []


def test_emergency_stop_aborts_and_releases_injected_key():
    sent = []
    guard = OwnedKeyboard(lambda key, pressed: sent.append((key, pressed)),
                          lambda key: False)
    guard.begin_session()
    def check():
        if sent:
            guard.release_all()
    with pytest.raises(InputStopped, match="Emergency"):
        guard.chord((0x11, 0x41), check)
    assert sent == [(0x11, True), (0x11, False)]
    with pytest.raises(InputStopped):
        guard.chord((0x09,), lambda: None)


def test_process_id_reuse_refused_even_when_hwnd_pid_and_name_match():
    bridge = object.__new__(WindowsDesktop)
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: 250.0
    before = observation()
    before.process_started_at = 100.0
    bridge._target = lambda *_args: pytest.fail("Refused process must not be targeted")
    with pytest.raises(DesktopUnavailable, match="PID was reused"):
        bridge.execute_observed(click(), before)


def test_observation_refuses_foreground_switch_during_uia_enumeration():
    bridge = object.__new__(WindowsDesktop)
    active = [(101, 24, "demo.exe", "Fixture")]
    bridge._foreground = lambda: active[0]
    bridge._process_started_at = lambda _pid: 100.0

    def enumerate_uia(_hwnd):
        active[0] = (202, 25, "foreign.exe", "Other")
        return [UIElement(automation_id="Save", control_type="Button")]

    bridge._elements = enumerate_uia
    with pytest.raises(DesktopUnavailable, match="changed"):
        bridge.observe(include_image=False)


def test_observation_refuses_process_reuse_during_uia_enumeration():
    bridge = object.__new__(WindowsDesktop)
    started = [100.0]
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: started[0]

    def enumerate_uia(_hwnd):
        started[0] = 250.0
        return []

    bridge._elements = enumerate_uia
    with pytest.raises(DesktopUnavailable, match="PID was reused"):
        bridge.observe(include_image=False)
