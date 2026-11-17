"""Fail-closed lifecycle transitions for reviewed desktop actions."""

import pytest

from piko.contracts import Session, SessionState
from piko.state import InvalidTransition, transition


def in_state(state):
    return Session(objective="Safe test", app_executable="demo.exe").model_copy(update={"state": state})


def test_allow_initial_observation():
    assert transition(in_state(SessionState.IDLE), SessionState.OBSERVING).state == SessionState.OBSERVING


def test_allow_cancel_before_first_action():
    assert transition(in_state(SessionState.IDLE), SessionState.CANCELLED).state == SessionState.CANCELLED


def test_allow_observation_to_analysis():
    assert transition(in_state(SessionState.OBSERVING), SessionState.ANALYZING).state == SessionState.ANALYZING


def test_allow_analysis_to_plan():
    assert transition(in_state(SessionState.ANALYZING), SessionState.PLANNING).state == SessionState.PLANNING


def test_require_user_review_after_planning():
    assert transition(in_state(SessionState.PLANNING), SessionState.WAITING_FOR_USER).state == SessionState.WAITING_FOR_USER
