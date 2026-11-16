"""Negative authorization and input ownership tests runnable off Windows."""
import threading

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
    bridge._native_dispatch_lock = threading.Lock()
    bridge._foreground = lambda: (202, 25, "evil.exe", "Other")
    bridge._target = lambda *_args: pytest.fail("Must not resolve a foreign UIA target")
    with pytest.raises(DesktopUnavailable, match="changed"):
        bridge.execute_observed(click(), observation())


def test_windows_bridge_requires_observed_hwnd():
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    with pytest.raises(DesktopUnavailable):
        bridge.execute_observed(click(), observation(hwnd=None))


def test_windows_bridge_uses_pinned_hwnd_and_uia_invoke():
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
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
    bridge._native_dispatch_lock = threading.Lock()
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


def test_emergency_releases_owned_key_while_foreground_check_is_hung():
    """Emergency key-up must not wait for an unresponsive native check."""
    sent = []
    check_entered = threading.Event()
    permit_check_to_finish = threading.Event()
    errors = []
    guard = OwnedKeyboard(lambda key, down: sent.append((key, down)),
                          lambda _key: False)
    guard.begin_session()

    def check_target():
        if len(sent) == 1:
            check_entered.set()
            assert permit_check_to_finish.wait(timeout=10)

    def worker():
        try:
            guard.chord((0x11, 0x41), check_target)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert check_entered.wait(timeout=3), "Worker did not reach blocked check"
        # While validation remains stuck, no new chord may begin.
        with pytest.raises(InputStopped, match="still active"):
            guard.begin_session()
        guard.release_all()
        assert sent == [(0x11, True), (0x11, False)]
    finally:
        permit_check_to_finish.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], InputStopped)
    # The old validation returning must not authorize the next key-down.
    assert sent == [(0x11, True), (0x11, False)]


def test_window_switch_during_target_lookup_refuses_invoke():
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    foreground = [(101, 24, "demo.exe", "Fixture")]
    bridge._foreground = lambda: foreground[0]
    invoked = []

    class Button:
        def is_enabled(self):
            return True

        def invoke(self):
            invoked.append("unsafe")

    def lookup(_automation_id, _hwnd):
        foreground[0] = (202, 25, "evil.exe", "Foreign")
        return Button()

    bridge._target = lookup
    with pytest.raises(DesktopUnavailable, match="changed"):
        bridge.execute_observed(click(), observation())
    assert invoked == []


def test_process_id_reuse_refused_even_when_hwnd_pid_and_name_match():
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: 250.0
    before = observation()
    before.process_started_at = 100.0
    bridge._target = lambda *_args: pytest.fail("Refused process must not be targeted")
    with pytest.raises(DesktopUnavailable, match="PID was reused"):
        bridge.execute_observed(click(), before)


def test_observation_refuses_foreground_switch_during_uia_enumeration():
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
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
    bridge._native_dispatch_lock = threading.Lock()
    started = [100.0]
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: started[0]

    def enumerate_uia(_hwnd):
        started[0] = 250.0
        return []

    bridge._elements = enumerate_uia
    with pytest.raises(DesktopUnavailable, match="PID was reused"):
        bridge.observe(include_image=False)


def test_emergency_stop_during_blocked_uia_lookup_prevents_later_invoke():
    """A cancelled COM lookup may return; it must not then click the UI."""
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._input_stopped = threading.Event()
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: 100.0
    class Keyboard:
        def release_all(self):
            pass
    bridge._keyboard = Keyboard()
    invoked = []
    class Button:
        def is_enabled(self):
            return True
        def invoke(self):
            invoked.append("unsafe")
    def lookup(_automation_id, _hwnd):
        bridge.emergency_release()
        return Button()
    bridge._target = lookup
    before = observation()
    before.process_started_at = 100.0
    with pytest.raises(DesktopUnavailable, match="Emergency stop"):
        bridge.execute_observed(click(), before)
    assert invoked == []


def test_emergency_stop_refuses_new_uia_actions_until_begin_session():
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._input_stopped = threading.Event()
    bridge._input_stopped.set()
    bridge._foreground = lambda: pytest.fail("Cancelled action must not inspect desktop")
    with pytest.raises(DesktopUnavailable, match="Emergency stop"):
        bridge.execute_observed(click(), observation())


def test_verification_failure_never_echoes_sensitive_selector():
    from piko.verification import verify

    secret = "name::Text::PRIVATE CUSTOMER NAME"
    before = observation()
    expectation = Expectation(automation_id=secret, property="exists")
    ok, reason = verify(expectation, before)
    assert not ok
    assert secret not in reason
    assert "PRIVATE" not in reason


def test_hung_uia_lookup_prevents_rearm_and_followup_dispatch_after_stop():
    """A blocked native lookup may finish late; no further input may escape."""
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._input_stopped = threading.Event()
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: 100.0
    observed = observation()
    observed.process_started_at = 100.0
    reached_com = threading.Event()
    unblock_com = threading.Event()
    invoked = []
    failures = []

    class Keyboard:
        def begin_session(self):
            pass

        def release_all(self):
            pass

    class Button:
        def is_enabled(self):
            return True

        def invoke(self):
            invoked.append("unexpected-native-invoke")

    bridge._keyboard = Keyboard()

    def simulate_blocked_uia_call(_name, _hwnd):
        reached_com.set()
        assert unblock_com.wait(timeout=10)
        return Button()

    bridge._target = simulate_blocked_uia_call

    def worker():
        try:
            bridge.execute_observed(click(), observed)
        except Exception as exc:
            failures.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert reached_com.wait(timeout=3), "Native worker did not enter blocked UIA lookup"
        bridge.emergency_release()
        # Input cannot be rearmed while old COM dispatch is in flight.
        with pytest.raises(DesktopUnavailable, match="still running"):
            bridge.begin_session()
        with pytest.raises(DesktopUnavailable, match="still running"):
            bridge.execute_observed(click(), observed)
        assert invoked == []
    finally:
        unblock_com.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], DesktopUnavailable)
    assert "Emergency stop" in str(failures[0])
    assert invoked == []
    # Once the old worker exits, cancellation remains latched until a fresh
    # authorized session explicitly begins. No queued action was retained.
    with pytest.raises(DesktopUnavailable, match="Emergency stop"):
        bridge.execute_observed(click(), observed)
    bridge.begin_session()
    bridge.execute_observed(click(), observed)
    assert invoked == ["unexpected-native-invoke"]


def test_hung_uia_property_lookup_cannot_type_after_emergency_cancel():
    """Text input has an independent just-before-dispatch stop check."""
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._input_stopped = threading.Event()
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: 100.0
    class Keyboard:
        def release_all(self):
            pass
    bridge._keyboard = Keyboard()
    typed = []

    class TargetInfo:
        @property
        def control_type(self):
            bridge.emergency_release()
            return "Edit"

    class TextInput:
        element_info = TargetInfo()

        def is_enabled(self):
            return True

        def set_edit_text(self, value):
            typed.append(value)

    bridge._target = lambda *_args: TextInput()
    action = Action(
        kind="ui.set_text", automation_id="Save", text="sensitive",
        expected=Expectation(
            automation_id="Save", property="text_equals", value="sensitive",
        ),
    )
    prior = observation()
    prior.process_started_at = 100.0
    with pytest.raises(DesktopUnavailable, match="Emergency stop"):
        bridge.execute_observed(action, prior)
    assert typed == []


def test_owned_keyboard_releases_previous_keys_after_native_injection_failure():
    sent = []

    def inject(key, down):
        if key == 0x41 and down:
            raise OSError("Simulated native injection failure")
        sent.append((key, down))

    guard = OwnedKeyboard(inject, lambda _key: False)
    guard.begin_session()
    with pytest.raises(OSError, match="injection failure"):
        guard.chord((0x11, 0x41), lambda: None)
    assert sent == [(0x11, True), (0x11, False)]


def test_native_dispatch_refuses_password_fields_before_target_resolution():
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._target = lambda *_args: pytest.fail("Password window must never resolve inputs")
    prior = observation()
    prior.elements.append(UIElement(
        automation_id="PasswordInput", control_type="Edit", is_password=True,
    ))
    with pytest.raises(DesktopUnavailable, match="password"):
        bridge.execute_observed(click(), prior)


@pytest.mark.parametrize("reason", [
    "UIA target not uniquely resolved (2 matches)",
    "UIA target not uniquely resolved (0 matches)",
    "UIA target is a password control",
])
def test_native_dispatch_refuses_inaccessible_ambiguous_or_secret_target(reason):
    bridge = object.__new__(WindowsDesktop)
    bridge._native_dispatch_lock = threading.Lock()
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")

    def deny(*_args):
        raise DesktopUnavailable(reason)

    bridge._target = deny
    with pytest.raises(DesktopUnavailable, match="UIA target"):
        bridge.execute_observed(click(), observation())


def test_teach_scoped_capture_refuses_changed_window_before_pixels():
    """Even a same-executable switch cannot reach UIA enumeration or mss."""
    bridge = object.__new__(WindowsDesktop)
    bridge._foreground = lambda: (202, 25, "demo.exe", "Other")
    bridge._elements = lambda _hwnd: pytest.fail(
        "Unauthorized screenshot must be rejected before UIA/pixel capture"
    )
    with pytest.raises(DesktopUnavailable, match="changed"):
        bridge.observe_scoped(observation(), include_image=True)


def test_teach_scoped_capture_rechecks_pid_lifetime_before_uia_enumeration():
    bridge = object.__new__(WindowsDesktop)
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: 300.0
    bridge._elements = lambda _hwnd: pytest.fail("Reused process must never be observed")
    approved = observation()
    approved.process_started_at = 100.0
    with pytest.raises(DesktopUnavailable, match="PID was reused"):
        bridge.observe_scoped(approved, include_image=True)


def test_teach_scoped_observation_preserves_authorized_foreground():
    bridge = object.__new__(WindowsDesktop)
    bridge._foreground = lambda: (101, 24, "demo.exe", "Fixture")
    bridge._process_started_at = lambda _pid: 100.0
    bridge._elements = lambda _hwnd: [
        UIElement(automation_id="Save", control_type="Button")
    ]
    approved = observation()
    approved.process_started_at = 100.0
    actual = bridge.observe_scoped(approved)
    assert actual.window_handle == approved.window_handle
    assert actual.process_id == approved.process_id
    assert actual.process_started_at == approved.process_started_at
    assert actual.elements[0].automation_id == "Save"
