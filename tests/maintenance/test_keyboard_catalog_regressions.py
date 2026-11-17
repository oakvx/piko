"""Safe application labels and user-owned keyboard input boundaries."""

import pytest

from piko.app_catalog import display_name
from piko.input_guard import InputStopped, OwnedKeyboard


def test_show_friendly_firefox_name():
    assert display_name("firefox.exe") == "Firefox"


def test_show_localized_notepad_name():
    assert display_name("notepad.exe") == "Blocco note"
