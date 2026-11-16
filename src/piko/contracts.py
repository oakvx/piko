"""Strict boundaries between model-generated intent and executable operations."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SessionState(StrEnum):
    IDLE = "idle"
    OBSERVING = "observing"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    PAUSED = "paused"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionKind(StrEnum):
    CLICK = "ui.click"
    SET_TEXT = "ui.set_text"
    HOTKEY = "keyboard.hotkey"
    WAIT = "wait.condition"


class Expectation(StrictModel):
    """A directly observable UIA property, not a language-model judgement."""
    automation_id: str = Field(min_length=1, max_length=128)
    property: Literal["exists", "text_equals", "text_contains", "enabled"]
    value: str | bool | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "Expectation":
        if self.property in {"text_equals", "text_contains"} and not isinstance(self.value, str):
            raise ValueError("Text expectations require a string value")
        if self.property == "enabled" and not isinstance(self.value, bool):
            raise ValueError("Enabled expectation requires a boolean")
        return self


class Action(StrictModel):
    kind: ActionKind
    automation_id: str | None = Field(default=None, max_length=128)
    text: str | None = Field(default=None, max_length=2000)
    keys: list[str] = Field(default_factory=list, max_length=3)
    timeout_seconds: float = Field(default=5, ge=0.1, le=15)
    expected: Expectation

    @model_validator(mode="after")
    def validate_action(self) -> "Action":
        if self.kind in {ActionKind.CLICK, ActionKind.SET_TEXT} and not self.automation_id:
            raise ValueError("UI actions require an automation_id")
        if self.kind == ActionKind.SET_TEXT and self.text is None:
            raise ValueError("Text action requires text")
        if self.kind == ActionKind.HOTKEY and not self.keys:
            raise ValueError("Hotkey action requires keys")
        if self.kind != ActionKind.HOTKEY and self.keys:
            raise ValueError("Unexpected keys")
        if self.kind != ActionKind.SET_TEXT and self.text is not None:
            raise ValueError("Unexpected text")
        return self


class Plan(StrictModel):
    objective: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=2000)
    actions: list[Action] = Field(min_length=1, max_length=12)


class UIElement(StrictModel):
    automation_id: str
    name: str = ""
    control_type: str = ""
    value: str | None = None
    enabled: bool = True
    is_password: bool = False
    # Screen coordinates from Windows UI Automation, not model-generated targets.
    bounds: tuple[int, int, int, int] | None = None


class Observation(StrictModel):
    timestamp: datetime = Field(default_factory=now)
    window_title: str
    process_id: int
    executable: str
    elements: list[UIElement]
    image_base64: str | None = Field(default=None, exclude=True)
    capture_bounds: tuple[int, int, int, int] | None = None


class ActionStatus(StrEnum):
    REQUESTED = "action_requested"
    DISPATCHED = "action_dispatched"
    EXECUTED = "action_executed"
    OUTCOME_OBSERVED = "outcome_observed"
    OUTCOME_VERIFIED = "outcome_verified"
    FAILED = "action_failed"


class ActionResult(StrictModel):
    status: ActionStatus
    explanation: str
    timestamp: datetime = Field(default_factory=now)


class Session(StrictModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    objective: str
    state: SessionState = SessionState.IDLE
    app_executable: str
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    plan: Plan | None = None
    next_action: int = 0
    error: str | None = None


class Event(StrictModel):
    type: str
    session_id: str
    timestamp: datetime = Field(default_factory=now)
    payload: dict[str, str | int | bool | float | None] = Field(default_factory=dict)


class AccessProfile(StrEnum):
    OBSERVE = "observe"
    LIMITED = "limited"
    FULL = "full"


class Grant(StrictModel):
    executable: str = Field(min_length=1)
    profile: AccessProfile = AccessProfile.LIMITED
    expires_at: datetime | None = None
    session_id: str | None = None

    @field_validator("executable")
    @classmethod
    def normalize_executable(cls, v: str) -> str:
        if "/" in v or "\\" in v:
            raise ValueError("Grant executable must be a basename, e.g. notepad.exe")
        return v.casefold()
