"""Optional REAL Ollama smoke test. No mocks, no implicit model downloads.

Run only in a controlled Windows environment with installed local Ollama:
  $env:PIKO_REAL_OLLAMA = '1'
  $env:PIKO_OLLAMA_REASONING_MODEL = '<installed structured-output model>'
  $env:PIKO_OLLAMA_VISION_MODEL = '<installed vision model>'
  python -m pytest -q tests/real/test_ollama_inference.py

The test fails on malformed models or inference; absence of prerequisites is
SKIPPED, never represented as successful real inference.
"""
from __future__ import annotations

import base64
import io
import os
import time

import pytest

from piko.contracts import Observation, UIElement
from piko.ollama import InferenceError, OllamaProvider


pytestmark = pytest.mark.skipif(
    os.environ.get("PIKO_REAL_OLLAMA") != "1",
    reason="Requires explicitly authorized local Ollama inference test",
)


@pytest.mark.asyncio
async def test_real_local_reasoning_model_generates_validated_plan():
    reasoning = os.environ.get("PIKO_OLLAMA_REASONING_MODEL")
    assert reasoning, "Set PIKO_OLLAMA_REASONING_MODEL to an installed local model"
    provider = OllamaProvider(reasoning_model=reasoning, timeout=120)
    try:
        installed = {model["name"] for model in await provider.models()}
        assert reasoning in installed, f"Reasoning model {reasoning} is not installed"
        observation = Observation(
            window_title="Controlled test interface",
            process_id=25,
            executable="demo.exe",
            elements=[
                UIElement(automation_id="SaveButton", control_type="Button",
                          name="Save", enabled=True),
                UIElement(automation_id="StatusLabel", control_type="Text",
                          name="Status", value="Waiting"),
            ],
        )
        started = time.perf_counter()
        plan = await provider.plan(
            "Click Save and verify that StatusLabel reads Done",
            observation,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert plan.actions, "Model returned no actions"
        assert all(action.automation_id in {"SaveButton", "StatusLabel", None}
                   for action in plan.actions)
        assert elapsed_ms > 0
        assert provider.last_latency_ms is not None
        assert provider.last_latency_ms > 0
        print(f"Real reasoning inference: {reasoning}, {elapsed_ms:.0f} ms")
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_real_local_vision_model_interprets_image():
    vision = os.environ.get("PIKO_OLLAMA_VISION_MODEL")
    if not vision:
        pytest.skip("No real vision model selected; set PIKO_OLLAMA_VISION_MODEL")
    reasoning = os.environ.get("PIKO_OLLAMA_REASONING_MODEL") or vision
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (400, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 35), "SAVE", fill="black")
    draw.text((20, 95), "Status: Waiting", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    observation = Observation(
        window_title="Controlled synthetic screenshot (real inference)",
        process_id=25,
        executable="demo.exe",
        elements=[],
        image_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
    )
    provider = OllamaProvider(reasoning_model=reasoning, vision_model=vision, timeout=120)
    try:
        installed = {model["name"] for model in await provider.models()}
        assert vision in installed, f"Vision model {vision} is not installed"
        capabilities = await provider.capabilities(vision)
        assert "vision" in capabilities, f"Model {vision} has no vision capability"
        started = time.perf_counter()
        summary = await provider.interpret(observation)
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert isinstance(summary, str) and summary.strip()
        assert provider.last_latency_ms is not None
        print(f"Real vision inference: {vision}, {elapsed_ms:.0f} ms")
    finally:
        await provider.close()
