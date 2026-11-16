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


@pytest.mark.asyncio
async def test_teach_same_executable_foreign_window_never_writes_second_frame(tmp_path):
    """Revocation must be per window/process instance, not executable basename."""
    import base64

    class SwitchingDesktop(EventDesktop):
        def __init__(self):
            super().__init__()
            self.captures = 0

        def observe(self, include_image=False):
            observed = super().observe(include_image=include_image)
            if include_image:
                self.captures += 1
                if self.captures > 1:
                    observed.window_handle = 222
                    observed.process_id = 82
                    observed.image_base64 = base64.b64encode(b"FOREIGN-SECRET").decode()
                else:
                    observed.image_base64 = base64.b64encode(b"CONSENTED-FRAME").decode()
            return observed

    root = tmp_path / "demonstrations"
    recorder = TeachRecorder(SwitchingDesktop(), root)
    identifier = await recorder.start("demo.exe", seconds=5)
    for _ in range(150):
        if recorder.active_id is None:
            break
        await asyncio.sleep(0.025)
    assert recorder.active_id is None, "Foreign HWND should terminate recording"
    manifest = recorder.get_latest()
    assert manifest["id"] == identifier
    assert manifest["frames"] == 1
    assert any(e["type"] == "capture.stopped" and e["reason"] == "window_changed"
               for e in manifest["events"])
    observations = [e["data"] for e in manifest["events"] if e["type"] == "observation"]
    assert len(observations) == 1
    assert observations[0]["frame_index"] == 0
    assert observations[0]["frame_file"] == "frame-0000.png"
    assert observations[0]["captured_at"]
    assert observations[0]["window_handle"] == 123
    assert (root / identifier / "frame-0000.png").read_bytes() == b"CONSENTED-FRAME"
    assert not (root / identifier / "frame-0001.png").exists()
    assert "FOREIGN-SECRET" not in json.dumps(manifest)


@pytest.mark.asyncio
async def test_teach_revoked_grant_stops_frames_and_rejects_future_input(tmp_path):
    from piko.contracts import AccessProfile, Grant
    from piko.permissions import PermissionManager

    perms = PermissionManager()
    perms.grant(Grant(executable="demo.exe", profile=AccessProfile.OBSERVE,
                      session_id="teach"))
    desktop = EventDesktop()
    root = tmp_path / "demonstrations"
    recorder = TeachRecorder(desktop, root)
    def authorize():
        perms.check_observe("demo.exe", "teach")

    identifier = await recorder.start("demo.exe", seconds=5, authorize_capture=authorize)
    for _ in range(120):
        if (root / identifier / "frame-0000.png").exists():
            break
        await asyncio.sleep(0.025)
    assert (root / identifier / "frame-0000.png").exists()
    # A revoked grant must not leave the input hook authorized, either.
    perms.revoke("demo.exe")
    recorder._enqueue_event({
        "type": "input.mouse_click", "x": 35, "y": 40, "button": "left",
    })
    for _ in range(150):
        if recorder.active_id is None:
            break
        await asyncio.sleep(0.025)
    assert recorder.active_id is None
    manifest = recorder.get_latest()
    assert manifest["frames"] == 1
    assert any(e["type"] == "capture.stopped"
               and e["reason"] == "authorization_lost"
               for e in manifest["events"])
    assert not any(e["type"] == "input.mouse_click" for e in manifest["events"])
    assert len(list((root / identifier).glob("frame-*.png"))) == 1


@pytest.mark.asyncio
async def test_teach_api_rechecks_grants_after_start(tmp_path):
    from piko.contracts import AccessProfile

    desktop = EventDesktop()
    app = create_app(token="p" * 32, reasoning_model="", desktop=desktop,
                     inference=Inference(), root=tmp_path)
    auth = {"Authorization": "Bearer " + "p" * 32}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        permission = await client.post("/permissions", headers=auth, json={
            "executable": "demo.exe", "profile": AccessProfile.OBSERVE,
            "session_id": "teach",
        })
        assert permission.status_code == 200
        started = await client.post(
            "/teach/start?seconds=5", headers=auth,
            json={"executable": "demo.exe", "session_id": "teach",
                  "profile": AccessProfile.OBSERVE},
        )
        assert started.status_code == 200, started.text
        identifier = started.json()["id"]
        for _ in range(120):
            if (tmp_path / "demonstrations" / identifier / "frame-0000.png").exists():
                break
            await asyncio.sleep(0.025)
        assert (tmp_path / "demonstrations" / identifier / "frame-0000.png").exists()
        revoked = await client.delete("/permissions/demo.exe", headers=auth)
        assert revoked.status_code == 200
        for _ in range(160):
            response = await client.get("/teach/status", headers=auth)
            if response.json()["recording"] is False:
                break
            await asyncio.sleep(0.025)
        assert response.json()["recording"] is False
        latest = app.state.teach.get_latest()
        summary = await client.get("/teach/latest", headers=auth)
        assert summary.status_code == 200
        assert summary.json()["stopped_reason"] == "authorization_lost"
        assert latest["frames"] == 1
        assert any(e["type"] == "capture.stopped" and
                   e["reason"] == "authorization_lost" for e in latest["events"])


@pytest.mark.asyncio
async def test_native_scoped_capture_denial_invalidates_recording(tmp_path):
    """A native refusal must stop Teach, not skip and resume on refocus."""
    from piko.windows import DesktopUnavailable

    class NativeScopedDesktop(EventDesktop):
        def __init__(self):
            super().__init__()
            self.captures = 0
            self.denied = False

        def observe_scoped(self, approved, include_image=False):
            assert approved.window_handle == 123
            assert approved.process_id == 81
            self.captures += 1
            if self.captures > 1:
                self.denied = True
                raise DesktopUnavailable("Foreground HWND no longer consented")
            return self.observe(include_image=include_image)

    root = tmp_path / "recordings"
    recorder = TeachRecorder(NativeScopedDesktop(), root)
    identifier = await recorder.start("demo.exe", seconds=5)
    for _ in range(150):
        if recorder.active_id is None:
            break
        await asyncio.sleep(0.025)
    assert recorder.active_id is None
    manifest = recorder.get_latest()
    assert manifest["id"] == identifier
    assert manifest["frames"] == 1
    assert any(event["type"] == "capture.stopped"
               and event["reason"] == "native_scope_denied"
               for event in manifest["events"])
    assert len(list((root / identifier).glob("frame-*.png"))) == 1
