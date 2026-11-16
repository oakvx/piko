"""Finite-state transitions; no unexamined resume after process restart."""
from piko.contracts import Session, SessionState, now


class InvalidTransition(ValueError):
    pass


TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.IDLE: frozenset({SessionState.OBSERVING, SessionState.CANCELLED}),
    SessionState.OBSERVING: frozenset({SessionState.ANALYZING, SessionState.FAILED, SessionState.CANCELLED}),
    SessionState.ANALYZING: frozenset({SessionState.PLANNING, SessionState.FAILED, SessionState.CANCELLED}),
    SessionState.PLANNING: frozenset({SessionState.WAITING_FOR_USER, SessionState.FAILED, SessionState.CANCELLED}),
    SessionState.WAITING_FOR_USER: frozenset({SessionState.EXECUTING, SessionState.CANCELLED}),
    SessionState.EXECUTING: frozenset({SessionState.VERIFYING, SessionState.PAUSED, SessionState.FAILED, SessionState.CANCELLED}),
    SessionState.VERIFYING: frozenset({SessionState.EXECUTING, SessionState.COMPLETED, SessionState.PAUSED, SessionState.FAILED, SessionState.CANCELLED}),
    SessionState.PAUSED: frozenset({SessionState.EXECUTING, SessionState.CANCELLED}),
    SessionState.COMPLETED: frozenset(),
    SessionState.FAILED: frozenset(),
    SessionState.CANCELLED: frozenset(),
}


def transition(session: Session, target: SessionState) -> Session:
    if target not in TRANSITIONS[session.state]:
        raise InvalidTransition(f"Invalid transition: {session.state} -> {target}")
    return session.model_copy(update={"state": target, "updated_at": now()})
