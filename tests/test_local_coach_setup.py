"""Local-only coaching and setup acceptance, with no internet or screen capture."""
import asyncio

import pytest

from piko.coach import LocalScreenCoach
from piko.contracts import Observation, UIElement
from piko.ollama import VisualInterpretation
from piko.setup import MODELS, SetupCoordinator


class ControlledGame:
    def __init__(self):
        self.frames = 0
        self.typed = 0

    def observe_window(self, hwnd, executable, include_image=False,
                       expected=None, window_pixels_only=False):
        assert hwnd == 1234 and executable == "game.exe"
        if include_image:
            assert window_pixels_only, "Coach must never capture the composited desktop"
        self.frames += bool(include_image)
        return Observation(window_title="Authorized Game", process_id=42,
                           executable=executable, window_handle=hwnd,
                           process_started_at=15.0, elements=[],
                           image_base64="dGVzdA==" if include_image else None)


class LocalVision:
    vision_model = "qwen3-vl:2b-instruct"
    reasoning_model = "qwen3:4b"

    def __init__(self):
        self.calls = []

    async def _chat(self, model, messages, schema):
        self.calls.append((model, messages))
        assert schema is VisualInterpretation
        assert messages[0]["images"] == ["dGVzdA=="]
        return VisualInterpretation(summary="Move left to avoid the obstacle")


@pytest.mark.asyncio
async def test_coach_requires_exact_target_and_does_not_inject_input():
    desktop, provider = ControlledGame(), LocalVision()
    coach = LocalScreenCoach(desktop, provider)
    with pytest.raises(ValueError):
        await coach.start("game.exe", 0)
    await coach.start("game.exe", 1234, seconds=30, interval_seconds=3)
    for _ in range(100):
        if coach.status()["frames"] > 0:
            break
        await asyncio.sleep(0.01)
    assert coach.status()["advice"] == "Move left to avoid the obstacle"
    assert coach.status()["active"]
    assert desktop.typed == 0
    assert len(provider.calls) == 1
    await coach.stop()
    assert not coach.status()["active"]
    assert coach.status()["stage"] == "stopped"


@pytest.mark.asyncio
async def test_coach_times_out_stalled_local_inference_without_persisting_pixels():
    class StalledVision(LocalVision):
        async def _chat(self, model, messages, schema):
            await asyncio.Event().wait()

    coach = LocalScreenCoach(
        ControlledGame(), StalledVision(), inference_timeout_seconds=0.05
    )
    try:
        await coach.start("game.exe", 1234, seconds=30, interval_seconds=3)
        async with asyncio.timeout(2):
            while coach.status()["stage"] != "temporarily-unavailable":
                await asyncio.sleep(0.01)
        state = coach.status()
        assert state["active"]
        assert state["error"] == "Local vision inference timed out"
        assert state["frames"] == 0
        assert state["last_inference_ms"] is None
        assert "image_base64" not in state
    finally:
        await coach.stop()
    assert coach.status()["stage"] == "stopped"


@pytest.mark.asyncio
async def test_coach_preserves_completed_advice_while_next_frame_is_analyzed():
    class TwoFrameVision(LocalVision):
        def __init__(self):
            super().__init__()
            self.calls_made = 0
            self.second_frame_started = asyncio.Event()

        async def _chat(self, model, messages, schema):
            self.calls_made += 1
            if self.calls_made == 1:
                return await super()._chat(model, messages, schema)
            self.second_frame_started.set()
            await asyncio.Event().wait()

    provider = TwoFrameVision()
    coach = LocalScreenCoach(ControlledGame(), provider)
    try:
        await coach.start("game.exe", 1234, seconds=30, interval_seconds=3)
        async with asyncio.timeout(7):
            await provider.second_frame_started.wait()
        state = coach.status()
        # The stage is transient: analyzing the next frame is not a stall.
        assert state["stage"] == "analyzing-locally"
        assert state["frames"] == 1
        assert state["advice"] == "Move left to avoid the obstacle"
        assert state["observed_at"]
        assert isinstance(state["last_inference_ms"], int)
        assert "image_base64" not in state
    finally:
        await coach.stop()
    assert coach.status()["stage"] == "stopped"


def test_setup_rejects_unknown_or_cloud_models(monkeypatch):
    from piko import setup as module
    monkeypatch.setattr(module, "hardware_profile", lambda: {
        "free_disk_gb": 100, "ram_gb": 16,
    })
    coordinator = SetupCoordinator(LocalVision(), lambda _vision: None)
    assert all(":cloud" not in tag for tag in MODELS)
    with pytest.raises(ValueError, match="approved local reasoning"):
        coordinator.start("arbitrary:cloud", None)
    with pytest.raises(ValueError, match="approved local vision"):
        coordinator.start("qwen3:4b", "arbitrary:cloud")
    assert coordinator.status()["stage"] == "idle"
    assert coordinator._task is None


def test_setup_rejects_insufficient_disk_space(monkeypatch):
    from piko import setup as module
    monkeypatch.setattr(module, "hardware_profile", lambda: {
        "free_disk_gb": 4.5, "ram_gb": 16,
    })
    coordinator = SetupCoordinator(LocalVision(), lambda _vision: None)
    with pytest.raises(ValueError, match="disk space"):
        coordinator.start("qwen3:8b", "qwen3-vl:2b-instruct")
    assert coordinator._task is None


def test_local_model_selection_survives_restart_and_rejects_cloud_or_invalid_tags(tmp_path):
    from piko.setup import load_model_selection, save_model_selection

    assert load_model_selection(tmp_path) == (None, None)
    save_model_selection(tmp_path, "qwen3:4b", "qwen3-vl:2b-instruct")
    assert load_model_selection(tmp_path) == ("qwen3:4b", "qwen3-vl:2b-instruct")
    with pytest.raises(ValueError):
        save_model_selection(tmp_path, "qwen3:4b-cloud", None)
    with pytest.raises(ValueError):
        save_model_selection(tmp_path, "../malicious", None)
    assert load_model_selection(tmp_path) == ("qwen3:4b", "qwen3-vl:2b-instruct")

    (tmp_path / "model-selection.json").write_text(
        '{"reasoning": "suspicious:cloud", "vision": null}'
    )
    assert load_model_selection(tmp_path) == (None, None)


def test_packaged_runtime_restores_selected_models_without_cloud_calls(tmp_path):
    from piko.api import create_app
    from piko.contracts import Observation
    from piko.setup import save_model_selection

    class FixtureDesktop:
        def observe(self, include_image=False):
            return Observation(window_title="fixture", process_id=1,
                               executable="fixture.exe", elements=[])
        def emergency_release(self):
            pass

    save_model_selection(tmp_path, "qwen3:4b", "qwen3-vl:2b-instruct")
    app = create_app(token="x" * 32, reasoning_model="",
                     desktop=FixtureDesktop(), root=tmp_path)
    try:
        assert app.state.agent.planner.reasoning_model == "qwen3:4b"
        assert app.state.agent.planner.vision_model == "qwen3-vl:2b-instruct"
        assert app.state.agent.vision is not None
    finally:
        app.state.agent.memory.close()
