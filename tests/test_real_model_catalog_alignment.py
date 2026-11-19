"""Real-model acceptance must test an Ollama model users can actually install.

No local models, screenshots or network access are needed for this check.
"""
from pathlib import Path

import yaml

from piko.setup import MODELS


ROOT = Path(__file__).resolve().parents[1]


def _real_model_environment():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/real-ollama.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["real-ollama-windows"]["env"]


def test_real_reasoning_model_is_supported_in_onboarding_catalog():
    model = _real_model_environment()["PIKO_OLLAMA_REASONING_MODEL"]
    assert model in MODELS
    assert MODELS[model][0] == "reasoning"


def test_real_vision_model_is_supported_in_onboarding_catalog():
    model = _real_model_environment()["PIKO_OLLAMA_VISION_MODEL"]
    assert model in MODELS
    assert MODELS[model][0] == "vision"


def test_real_ollama_acceptance_disables_cloud_and_requires_explicit_mode():
    env = _real_model_environment()
    assert env["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert env["OLLAMA_NO_CLOUD"] == "1"
    assert env["PIKO_REAL_OLLAMA"] == "1"
    assert env["PIKO_GUI_SMOKE"] == "1"
