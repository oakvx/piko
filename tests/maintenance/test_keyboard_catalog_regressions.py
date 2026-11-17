"""Safe application labels and user-owned keyboard input boundaries."""

import pytest

from piko.app_catalog import display_name
from piko.input_guard import InputStopped, OwnedKeyboard


def test_show_friendly_firefox_name():
    assert display_name("firefox.exe") == "Firefox"


def test_show_localized_notepad_name():
    assert display_name("notepad.exe") == "Blocco note"


def test_present_unrecognized_executable_humanely():
    assert display_name("household_tool.exe") == "Household Tool"


def test_normalize_known_executable_case_for_display():
    assert display_name("FIREFOX.EXE") == "Firefox"


def test_bound_display_label_length():
    label = display_name("a" * 100 + ".exe")
    assert len(label) <= 70


def test_release_injected_chord_in_reverse_order():
    events = []
    keyboard = OwnedKeyboard(lambda key, down: events.append((key, down)), lambda key: False)
    keyboard.begin_session()
    keyboard.chord((17, 87), lambda: None)
    assert events == [(17, True), (87, True), (87, False), (17, False)]
