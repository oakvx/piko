"""Teach Mode scoped input timeline and corrected Skill generation tests."""
import asyncio
import json

import httpx
import pytest

from piko.api import create_app
from piko.contracts import Observation, UIElement
from piko.teach import TeachRecorder


class EventDesktop:
    def __init__(self):
        self.callback = None
        self.stopped = False
    def observe(self, include_image=False):
        return Observation(
            window_title="Sensitive document title",
            process_id=81,
            window_handle=123,
            executable="demo.exe",
            elements=[
                UIElement(automation_id="Save", name="Save", control_type="Button",
                          bounds=(0, 0, 100, 100)),
                UIElement(automation_id="Status", name="private info", value="SECRET-VALUE",
                          control_type="Text", bounds=(110, 0, 300, 50)),
                UIElement(automation_id="name::Button::SENSITIVE-FALLBACK",
                          name="SENSITIVE-BUTTON-LABEL", control_type="Button",
                          bounds=(200, 150, 250, 190)),
            ],
            image_base64="YQ==" if include_image else None,
        )
    def start_teach_events(self, executable, hwnd, callback):
        assert executable == "demo.exe" and hwnd == 123
        self.callback = callback
        def stop():
            self.stopped = True
        return stop
    def execute(self, action): pass
    def emergency_release(self): pass


class Inference:
    async def close(self): pass


async def make_recording(root):
    desktop = EventDesktop()
    recorder = TeachRecorder(desktop, root)
    identifier = await recorder.start("demo.exe", seconds=3)
    for _ in range(60):
        if list((root / identifier).glob("frame-*.png")):
            break
        await asyncio.sleep(0.025)
    assert list((root / identifier).glob("frame-*.png"))
    desktop.callback({"type": "input.mouse_click", "button": "left", "x": 35, "y": 40})
    manifest = await recorder.stop()
    assert desktop.stopped
    return identifier, manifest, recorder


@pytest.mark.asyncio
async def test_teach_scoped_timeline_and_tentative_uia_grounding(tmp_path):
    identifier, manifest, recorder = await make_recording(tmp_path / "demonstrations")
    recorded = json.dumps(manifest)
    assert "SECRET-VALUE" not in recorded
    assert "Sensitive document title" not in recorded
    assert "private info" not in recorded
    assert "SENSITIVE-FALLBACK" not in recorded
    assert "SENSITIVE-BUTTON-LABEL" not in recorded
    assert "input.mouse_click" in recorded
    analysis = recorder.analyze(identifier)
    assert analysis["input_events"] == 1
    assert analysis["steps"][0]["automation_id"] == "Save"
    assert analysis["steps"][0]["confidence"] == "tentative"
    assert analysis["status"] == "needs_review"
    assert {tuple(item.values()) for item in analysis["observed_targets"]} >= {
        ("Save", "Button"), ("Status", "Text"),
    }
    # Dynamic name-derived identifiers and user-visible text never become
    # reusable selector suggestions.
    assert all("SENSITIVE" not in item["automation_id"]
               for item in analysis["observed_targets"])


@pytest.mark.asyncio
async def test_teach_user_correction_requires_outcome_and_explicit_confirmation(tmp_path):
    identifier, _, _ = await make_recording(tmp_path / "demonstrations")
    app = create_app(token="z"*32, reasoning_model="",
                     desktop=EventDesktop(), inference=Inference(), root=tmp_path)
    auth = {"Authorization": "Bearer " + "z"*32}
    body = {
        "slug": "observed-save", "description": "Saved demo with corrected expected outcome",
        "confirmed_user_corrections": True,
        "plan": {
            "objective": "Save demo", "explanation": "Corrected click",
            "actions": [{
                "kind": "ui.click", "automation_id": "Save",
                "expected": {"automation_id": "Status", "property": "text_equals", "value": "Saved"},
            }],
        },
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://test") as client:
        url = f"/teach/{identifier}/draft"
        missing = {**body, "confirmed_user_corrections": False}
        assert (await client.post(url, headers=auth, json=missing)).status_code == 403
        weak = json.loads(json.dumps(body))
        weak["plan"]["actions"][-1]["expected"] = {"automation_id": "Save", "property": "exists"}
        assert (await client.post(url, headers=auth, json=weak)).status_code == 409
        unobserved_outcome = json.loads(json.dumps(body))
        unobserved_outcome["plan"]["actions"][-1]["expected"]["automation_id"] = "UnknownStatus"
        blocked = await client.post(url, headers=auth, json=unobserved_outcome)
        assert blocked.status_code == 409
        assert "unobserved" in blocked.json()["detail"]
        response = await client.post(url, headers=auth, json=body)
        assert response.status_code == 200
        assert response.json()["verified"] is False
        assert response.json()["status"] == "draft"
        assert len((await client.get("/skills", headers=auth)).json()) == 1


@pytest.mark.asyncio
async def test_teach_only_saves_allowlisted_input_fields(tmp_path):
    recorder = TeachRecorder(EventDesktop(), tmp_path / "demonstrations")
    await recorder.start("demo.exe", seconds=3)
    recorder._enqueue_event({
        "type": "input.mouse_click", "button": "left", "x": 35, "y": 40,
        "text": "EXFILTRATE-SECRET", "clipboard": "EXFILTRATE-SECRET",
    })
    recorder._enqueue_event({
        "type": "input.special_key", "key": "a", "text": "EXFILTRATE-SECRET",
    })
    recorder._enqueue_event({"type": "input.secret", "value": "EXFILTRATE-SECRET"})
    manifest = await recorder.stop()
    serialized = json.dumps(manifest)
    assert "EXFILTRATE-SECRET" not in serialized
    assert len([e for e in manifest["events"] if e["type"] == "input.mouse_click"]) == 1
    assert not any(e["type"] == "input.secret" for e in manifest["events"])


def test_teach_queue_is_bounded_under_input_flood(tmp_path):
    from piko.teach import MAX_PENDING_INPUT_EVENTS

    recorder = TeachRecorder(EventDesktop(), tmp_path / "demonstrations")
    recorder.active_id = "synthetic-test"
    for _ in range(MAX_PENDING_INPUT_EVENTS + 20):
        recorder._enqueue_event({
            "type": "input.mouse_scroll", "x": 5, "y": 10, "dx": 0, "dy": 1,
        })
    assert recorder._event_queue.qsize() == MAX_PENDING_INPUT_EVENTS
    assert recorder._dropped_input_events == 20
    recorder._drain_events()
    assert recorder._recorded_input_events == MAX_PENDING_INPUT_EVENTS
    assert len(recorder._events) == MAX_PENDING_INPUT_EVENTS
