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


def test_reject_unobserved_selector():
    ok, reason = verify(expected(), observe(UIElement(automation_id="Other")))
    assert not ok and "unavailable" in reason


def test_reject_duplicate_ambiguous_selector():
    elements = [UIElement(automation_id="Status"), UIElement(automation_id="Status")]
    ok, reason = verify(expected(), observe(*elements))
    assert not ok and "2 matches" in reason


def test_verify_enabled_true_against_visible_element():
    ok, _ = verify(expected("enabled", True), observe(UIElement(automation_id="Status", enabled=True)))
    assert ok


def test_verify_enabled_false_against_disabled_element():
    ok, _ = verify(expected("enabled", False), observe(UIElement(automation_id="Status", enabled=False)))
    assert ok


def test_reject_incorrect_enabled_state():
    ok, reason = verify(expected("enabled", False), observe(UIElement(automation_id="Status", enabled=True)))
    assert not ok and "did not match" in reason


def test_compare_exact_uia_value():
    el = UIElement(automation_id="Status", value="Saved")
    assert verify(expected("text_equals", "Saved"), observe(el))[0]


def test_compare_exact_accessible_name():
    el = UIElement(automation_id="Status", name="Saved", value="Pending")
    assert verify(expected("text_equals", "Saved"), observe(el))[0]


def test_match_substring_in_accessible_name_when_value_empty():
    el = UIElement(automation_id="Status", name="Saved successfully", value="")
    assert verify(expected("text_contains", "success"), observe(el))[0]


def test_compare_window_title_reference_without_uia_target():
    before = expected("window_title_changed", "Original", target="@window")
    assert verify(before, observe(title="Updated"))[0]
    assert not verify(before, observe(title="Original"))[0]
