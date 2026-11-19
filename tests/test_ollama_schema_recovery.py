"""Offline regressions for real Ollama schema failures observed on Windows.

These tests mock the HTTP TRANSPORT only; they are not evidence of model
inference. The separate Windows real-Ollama workflow still must pass.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from piko.contracts import Observation, UIElement
from piko.ollama import GeneratedPlan, GeneratedWirePlan, InferenceError, OllamaProvider


class FakeResponse:
    def __init__(self, content: str):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self.content}}


class FakeClient:
    def __init__(self, replies: list[str]):
        self.replies = replies
        self.payloads: list[dict] = []

    async def post(self, path: str, json: dict):
        assert path == "/api/chat"
        self.payloads.append(json)
        return FakeResponse(self.replies.pop(0))

    async def aclose(self):
        pass


def example_observation() -> Observation:
    return Observation(
        executable="demo.exe", process_id=1, window_title="Controlled",
        elements=[
            UIElement(automation_id="SaveButton", control_type="Button", name="Save"),
            UIElement(automation_id="StatusLabel", control_type="Text", value="Waiting"),
        ],
    )


@pytest.mark.asyncio
async def test_invalid_click_schema_retries_then_accepts_only_validated_plan():
    # The original real 1.5b model omitted automation_id and added text to
    # an action that cannot contain it. The first output MUST NOT execute.
    invalid = json.dumps({
        "objective": "Save", "explanation": "Click",
        "actions": [{"kind": "ui.click", "text": "Click Save",
                     "expected": {"automation_id": "StatusLabel",
                                  "property": "text_equals", "value": "Done"}}],
    })
    valid = json.dumps({
        "objective": "Save", "explanation": "Click the observed button",
        "actions": [{"kind": "ui.click", "automation_id": "SaveButton",
                     "expected": {"automation_id": "StatusLabel",
                                  "property": "text_equals", "value": "Done"}}],
    })
    provider = OllamaProvider("local-text")
    fake = FakeClient([invalid, valid])
    provider.client = fake
    try:
        plan = await provider.plan("Click Save and verify Done", example_observation())
        assert len(plan.actions) == 1
        assert plan.actions[0].automation_id == "SaveButton"
        assert len(fake.payloads) == 2
        assert "schema validation" in fake.payloads[1]["messages"][-1]["content"]
        assert fake.payloads[0]["options"]["num_predict"] == 2048
        assert provider.last_latency_ms is not None and provider.last_latency_ms >= 0
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_vision_summary_is_bounded_and_repaired_with_one_retry():
    provider = OllamaProvider("text", vision_model="vision")
    provider.capabilities = AsyncMock(return_value=["vision"])
    fake = FakeClient([
        json.dumps({"summary": "verbose " * 80}),
        json.dumps({"summary": "SAVE button. Status: Waiting."}),
    ])
    provider.client = fake
    try:
        image = example_observation().model_copy(update={"image_base64": "aGVsbG8="})
        summary = await provider.interpret(image)
        assert "SAVE" in summary and "Waiting" in summary
        assert len(fake.payloads) == 2
        assert fake.payloads[0]["options"]["num_predict"] == 256
        assert "at most 25 words" in fake.payloads[0]["messages"][0]["content"]
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_three_invalid_model_outputs_fail_closed_without_leaking_raw_text():
    sensitive = "PRIVATE_SCREEN_TEXT"
    invalid = json.dumps({
        "objective": "Do task", "explanation": sensitive,
        "actions": [{"kind": "ui.click", "text": sensitive, "expected": {
            "automation_id": "StatusLabel", "property": "exists"}}],
    })
    provider = OllamaProvider("local-text")
    fake = FakeClient([invalid, invalid, invalid])
    provider.client = fake
    try:
        with pytest.raises(InferenceError) as error:
            await provider.plan("Click Save", example_observation())
        assert sensitive not in str(error.value)
        assert "schema validation" in str(error.value)
        assert len(fake.payloads) == 3
    finally:
        await provider.close()


def test_flat_generation_hint_avoids_discriminated_union_without_bypassing_validation():
    # Small real Qwen models sometimes leave out the oneOf discriminator
    # when Ollama tries to synthesize a discriminated union directly.
    wire = GeneratedWirePlan.model_json_schema()
    actions = wire["properties"]["actions"]["items"]
    assert "oneOf" not in actions
    assert "discriminator" not in actions
    flat = wire["$defs"]["GeneratedWireAction"]
    assert {"kind", "expected"} <= set(flat["required"])
    assert "ui.click" in flat["properties"]["kind"]["enum"]
    # The authoritative executable schema remains discriminated and strict.
    strict = GeneratedPlan.model_json_schema()
    assert strict["properties"]["actions"]["items"]["discriminator"]["propertyName"] == "kind"


@pytest.mark.asyncio
async def test_flat_wire_hint_still_rejects_missing_kind_and_selectors():
    # This mirrors the safe structural failure categories seen in real CI,
    # without persisting any model output or private UI observations.
    payload = json.dumps({
        "objective": "Click Save", "explanation": "One action",
        "actions": [{"expected": {
            "automation_id": "StatusLabel", "property": "text_equals", "value": "Done",
        }}],
    })
    provider = OllamaProvider("qwen2.5:3b")
    fake = FakeClient([payload, payload, payload])
    provider.client = fake
    try:
        with pytest.raises(InferenceError, match="union_tag_not_found"):
            await provider.plan("Click Save", example_observation())
        assert len(fake.payloads) == 3
        assert fake.payloads[0]["format"] == GeneratedPlan.model_json_schema()
        assert fake.payloads[1]["format"] == GeneratedPlan.model_json_schema()
        assert fake.payloads[2]["format"] == GeneratedWirePlan.model_json_schema()
        assert "discriminator" not in fake.payloads[2]["format"]["properties"]["actions"]["items"]
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_flat_wire_hint_does_not_authorize_extraneous_click_fields():
    invalid = json.dumps({
        "objective": "Click Save", "explanation": "One action",
        "actions": [{"kind": "ui.click", "automation_id": "SaveButton",
                     "text": "surreptitious input", "expected": {
                         "automation_id": "StatusLabel",
                         "property": "text_equals", "value": "Done",
                     }}],
    })
    provider = OllamaProvider("qwen2.5:3b")
    fake = FakeClient([invalid, invalid])
    provider.client = fake
    try:
        with pytest.raises(InferenceError, match="schema validation"):
            await provider.plan("Click Save", example_observation())
        assert len(fake.payloads) == 3
    finally:
        await provider.close()


def test_model_facing_schema_requires_ui_selector_and_forbids_click_text():
    schema = GeneratedPlan.model_json_schema()
    variants = schema["properties"]["actions"]["items"]
    assert variants["discriminator"]["propertyName"] == "kind"
    assert len(variants["oneOf"]) == 4
    click = schema["$defs"]["GeneratedClick"]
    typing = schema["$defs"]["GeneratedSetText"]
    assert {"kind", "automation_id", "expected"} <= set(click["required"])
    assert "text" not in click["properties"]
    assert "keys" not in click["properties"]
    assert {"kind", "automation_id", "text", "expected"} <= set(typing["required"])
    assert "keys" not in typing["properties"]
    assert "text" not in schema["$defs"]["GeneratedWait"]["properties"]
    assert "text" not in schema["$defs"]["GeneratedHotkey"]["properties"]


@pytest.mark.asyncio
async def test_plan_rejects_hallucinated_expectation_target():
    payload = json.dumps({
        "objective": "Save", "explanation": "Click observed button",
        "actions": [{
            "kind": "ui.click", "automation_id": "SaveButton",
            "expected": {
                "automation_id": "InventedLabel", "property": "text_equals", "value": "Done",
            },
        }],
    })
    provider = OllamaProvider("local-text")
    fake = FakeClient([payload])
    provider.client = fake
    try:
        with pytest.raises(InferenceError, match="verification selector"):
            await provider.plan("Click Save", example_observation())
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_qwen_json_generation_disables_thinking_and_uses_strict_retry():
    malformed = '{"objective":'
    valid = json.dumps({
        "objective": "Save", "explanation": "Click the observed button",
        "actions": [{"kind": "ui.click", "automation_id": "SaveButton",
                     "expected": {"automation_id": "StatusLabel",
                                  "property": "text_equals", "value": "Done"}}],
    })
    provider = OllamaProvider("qwen3:4b")
    fake = FakeClient([malformed, valid])
    provider.client = fake
    try:
        plan = await provider.plan("Click Save and verify Done", example_observation())
        assert plan.actions[0].automation_id == "SaveButton"
        assert len(fake.payloads) == 2
        assert all(payload["think"] is False for payload in fake.payloads)
        assert isinstance(fake.payloads[0]["format"], dict)
        assert fake.payloads[0]["format"] == GeneratedPlan.model_json_schema()
        assert fake.payloads[1]["format"] == GeneratedPlan.model_json_schema()
        assert all(payload["stream"] is False for payload in fake.payloads)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_explicit_firefox_tab_close_is_reviewed_typed_plan_without_model():
    from piko.contracts import Grant
    from piko.permissions import PermissionManager
    from piko.verification import verify

    provider = OllamaProvider("qwen3:4b")
    fake = FakeClient([])  # Any call to Ollama would fail the test.
    provider.client = fake
    old = Observation(
        executable="firefox.exe", process_id=15, window_handle=840,
        process_started_at=123.5, window_title="Example tab — Mozilla Firefox",
        elements=[],
    )
    try:
        route = await provider.plan("chiudi la scheda", old)
        assert not fake.payloads
        assert len(route.actions) == 1
        action = route.actions[0]
        assert action.kind.value == "keyboard.hotkey"
        assert action.keys == ["ctrl", "w"]
        assert action.expected.automation_id == "@window"
        assert action.expected.property == "window_title_changed"
        assert action.expected.value == old.window_title
        assert not verify(action.expected, old)[0]
        assert verify(action.expected, old.model_copy(update={
            "window_title": "New tab — Mozilla Firefox",
        }))[0]

        permissions = PermissionManager()
        permissions.grant(Grant(executable=old.executable, session_id="reviewed"))
        permissions.check(old.executable, "reviewed", action)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_tab_close_intent_never_authorizes_other_apps_or_extra_instructions():
    provider = OllamaProvider("qwen3:4b")
    fake = FakeClient(['not-json'] * 6)
    provider.client = fake
    try:
        notepad = Observation(
            executable="notepad.exe", process_id=2, window_title="Notepad",
            elements=[],
        )
        with pytest.raises(InferenceError, match="schema validation"):
            await provider.plan("chiudi la scheda", notepad)
        assert len(fake.payloads) == 3
        firefox = notepad.model_copy(update={
            "executable": "firefox.exe", "window_title": "Example - Firefox",
        })
        with pytest.raises(InferenceError, match="schema validation"):
            await provider.plan("non chiudere la scheda", firefox)
        assert len(fake.payloads) == 6
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_browser_tab_close_skips_vision_capture_and_waits_for_route_review(tmp_path):
    from piko.contracts import Grant, SessionState
    from piko.memory import LocalMemory
    from piko.orchestrator import Agent
    from piko.permissions import PermissionManager

    class BrowserDesktop:
        def __init__(self):
            self.capture_requested = False

        def observe(self, include_image=False):
            self.capture_requested |= include_image
            return Observation(executable="firefox.exe", process_id=9,
                               window_title="Release preview — Mozilla Firefox",
                               elements=[])

    desktop = BrowserDesktop()
    model = OllamaProvider("qwen3:4b", vision_model="qwen3-vl:2b-instruct")
    model.client = FakeClient([])  # Neither role may be called.
    memory = LocalMemory(tmp_path / "safe-shortcut.db")
    permission = PermissionManager()
    agent = Agent(desktop, model, memory, permission, vision=model.interpret)
    try:
        session = agent.create("chiudi la scheda", "firefox.exe")
        permission.grant(Grant(executable="firefox.exe", session_id=session.id))
        prepared = await agent.prepare(session.id)
        assert prepared.state == SessionState.WAITING_FOR_USER
        assert prepared.plan is not None
        assert prepared.plan.actions[0].keys == ["ctrl", "w"]
        assert not desktop.capture_requested
        assert not model.client.payloads
    finally:
        await model.close()
        memory.close()
