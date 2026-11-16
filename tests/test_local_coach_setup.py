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
