"""Verification requires a unique fresh semantic observation."""

from piko.contracts import Expectation, Observation, UIElement
from piko.verification import verify


def observe(*elements, title="Demo"):
    return Observation(window_title=title, executable="demo.exe", process_id=10,
                       elements=list(elements))


def expected(property="exists", value=None, target="Status"):
    return Expectation(automation_id=target, property=property, value=value)


def test_verify_single_existing_element():
    ok, reason = verify(expected(), observe(UIElement(automation_id="Status")))
    assert ok and reason == "UI element observed"
