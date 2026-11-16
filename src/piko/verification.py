"""Verification requires a fresh observation of the expected semantic UI state."""
from piko.contracts import Expectation, Observation


def verify(expectation: Expectation, observation: Observation) -> tuple[bool, str]:
    matches = [e for e in observation.elements if e.automation_id == expectation.automation_id]
    if len(matches) != 1:
        return False, f"Verification UIA target is ambiguous or unavailable ({len(matches)} matches)"
    element = matches[0]
    if expectation.property == "exists":
        return True, "UI element observed"
    if expectation.property == "enabled":
        result = element.enabled == expectation.value
    elif expectation.property == "text_equals":
        result = element.value == expectation.value or element.name == expectation.value
    elif expectation.property == "text_contains":
        result = str(expectation.value) in (element.value or element.name)
    else:
        return False, "Unsupported verification property"
    return result, "Observed expected state" if result else "UI state did not match expectation"
