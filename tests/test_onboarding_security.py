"""Security regression gates for first-run Ollama and private screen coaching.

The installer checks are deliberately offline: simulated signed/unsigned
executables MUST NEVER be launched on a developer or GitHub CI machine.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from piko import setup
from piko.coach import LocalScreenCoach
from piko.contracts import Observation


class FakeResponse:
    def __init__(self, final_url: str):
        self.final_url = final_url
        self.headers = {"Content-Length": "8"}
        self._read = False

    def geturl(self):
        return self.final_url

    def read(self, _chunk_size):
        if self._read:
            return b""
        self._read = True
        return b"12345678"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.fixture
def offline_ollama_installer(monkeypatch):
    """Mock only the external boundaries, not Piko's signature gate."""
    monkeypatch.setattr(setup.sys, "platform", "win32")
    runs = []
    fetched = []
    url = {"value": "https://ollama.com/download/OllamaSetup.exe"}
    valid_signature = {"value": False}

    def fake_urlopen(request, timeout):
        assert request.full_url == setup.INSTALLER_URL
        assert timeout == 60
        fetched.append(request.full_url)
        return FakeResponse(url["value"])

    def fake_subprocess_run(args, **kwargs):
        runs.append(list(args))
        if args[0] == "powershell.exe":
            assert "Get-AuthenticodeSignature" in args[-1]
            assert "Ollama" in args[-1]
            assert "PIKO_SETUP_EXE" in kwargs["env"]
            return SimpleNamespace(returncode=0 if valid_signature["value"] else 1)
        if Path(args[0]).name == "OllamaSetup.exe":
            assert valid_signature["value"], "Unsigned binaries must never execute"
            assert "/VERYSILENT" in args
            return SimpleNamespace(returncode=0)
        raise AssertionError("Unexpected external subprocess")

    monkeypatch.setattr(setup.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(setup.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(setup, "find_ollama_binary", lambda: Path("C:/Program Files/Ollama/ollama.exe"))
    return url, valid_signature, runs, fetched


def test_unsigned_ollama_installer_is_not_executed(offline_ollama_installer):
    _, _, runs, _ = offline_ollama_installer
    updates = []
    with pytest.raises(RuntimeError, match="Authenticode signature verification failed"):
        setup.install_official_ollama(lambda stage, progress: updates.append(stage))
    assert len(runs) == 1
    assert runs[0][0] == "powershell.exe"
    assert "verifying-signature" in updates
    assert "installing-runtime" not in updates


def test_untrusted_runtime_redirect_never_executes(offline_ollama_installer):
    url, _, runs, fetched = offline_ollama_installer
    url["value"] = "https://evil.example/redirected-setup.exe"
    with pytest.raises(RuntimeError, match="unapproved origin"):
        setup.install_official_ollama(lambda *_: None)
    assert fetched == [setup.INSTALLER_URL]
    assert runs == []


def test_signed_installer_is_only_executed_after_signature_gate(offline_ollama_installer):
    _, valid_signature, runs, _ = offline_ollama_installer
    valid_signature["value"] = True
    states = []
    setup.install_official_ollama(lambda stage, progress: states.append(stage))
    assert [Path(cmd[0]).name for cmd in runs] == ["powershell.exe", "OllamaSetup.exe"]
    assert states.index("verifying-signature") < states.index("installing-runtime")


class ScopableGame:
    def __init__(self, *, foreground: bool = True, replaced: bool = False):
        self.foreground = foreground
        self.replaced = replaced
        self.captures = 0
        self.initial_observation = False

    def is_window_foreground(self, hwnd):
        assert hwnd == 404
        return self.foreground

    def observe_window(self, hwnd, exe, include_image=False, expected=None, window_pixels_only=False):
        assert hwnd == 404 and exe == "game.exe"
        if include_image:
            assert window_pixels_only, "Game coaching may not grab the entire desktop"
            assert expected is not None
            if self.replaced:
                raise RuntimeError("Selected window changed process; operation refused")
            self.captures += 1
        self.initial_observation = True
        return Observation(executable=exe, window_title="Test Game", process_id=7,
                           window_handle=hwnd, process_started_at=100.0,
                           elements=[], image_base64="ZmFrZQ==" if include_image else None)


class LocalVisionOnly:
    vision_model = "qwen3-vl:2b-instruct"

    def __init__(self):
        self.calls = 0

    async def _chat(self, model, messages, schema):
        self.calls += 1
        raise AssertionError("Foreground or replaced-window gate should forbid visual inference")


@pytest.mark.asyncio
async def test_coach_waits_without_capturing_when_game_is_in_background():
    game, inference = ScopableGame(foreground=False), LocalVisionOnly()
    coach = LocalScreenCoach(game, inference)
    await coach.start("game.exe", 404, seconds=30, interval_seconds=3)
    try:
        for _ in range(40):
            if coach.status()["stage"] == "waiting-for-game":
                await asyncio.sleep(0.01)
        assert game.initial_observation
        assert game.captures == 0
        assert inference.calls == 0
        assert coach.status()["frames"] == 0
    finally:
        await coach.stop()
    assert not coach.status()["active"]
    assert coach.status()["stage"] == "stopped"


@pytest.mark.asyncio
async def test_coach_stops_on_replaced_window_without_any_inference():
    game, inference = ScopableGame(replaced=True), LocalVisionOnly()
    coach = LocalScreenCoach(game, inference)
    await coach.start("game.exe", 404, seconds=30, interval_seconds=3)
    try:
        for _ in range(100):
            if coach.status()["stage"] == "stopped-safely":
                break
            await asyncio.sleep(0.01)
        assert coach.status()["stage"] == "stopped-safely"
        assert coach.status()["active"] is False
        assert game.captures == 0
        assert inference.calls == 0
    finally:
        await coach.stop()
