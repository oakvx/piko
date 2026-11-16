"""Explicit local-first Ollama setup and conservative hardware recommendations.

Nothing is downloaded without a user's explicit /setup/install action.
No screenshot, prompt, input, machine identifier, or model inference is sent
anywhere except the local Ollama loopback. Only model binaries are downloaded
from the Ollama registry by the local Ollama daemon.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import httpx

from piko.ollama import OllamaProvider, check_service


MODELS = {
    "qwen2.5:1.5b": ("reasoning", 1.0),
    "qwen3:4b": ("reasoning", 2.5),
    "qwen3:8b": ("reasoning", 5.2),
    "qwen3-vl:2b-instruct": ("vision", 1.9),
}
INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"


def hardware_profile() -> dict:
    """Use local, coarse RAM/GPU facts; never upload a hardware fingerprint."""
    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
        cpu = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
    except ImportError:
        ram_gb = 8.0
        cpu = os.cpu_count() or 1
    gpu_vram_gb = None
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
        gpu_vram_gb = round(max(float(x.strip()) for x in output.splitlines()
                                if x.strip()) / 1024, 1)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    free_gb = round(shutil.disk_usage(Path.home()).free / (1024 ** 3), 1)
    # Conservative CPU defaults for machines whose GPU VRAM cannot be verified.
    if ram_gb < 8 or free_gb < 8:
        reasoning = "qwen2.5:1.5b"
        vision = None
    elif ram_gb >= 16 and gpu_vram_gb is not None and gpu_vram_gb >= 8:
        reasoning = "qwen3:8b"
        vision = "qwen3-vl:2b-instruct"
    else:
        reasoning = "qwen3:4b"
        vision = "qwen3-vl:2b-instruct" if ram_gb >= 12 and free_gb >= 10 else None
    return {
        "ram_gb": ram_gb, "cpu_cores": cpu, "gpu_vram_gb": gpu_vram_gb,
        "free_disk_gb": free_gb, "reasoning_model": reasoning,
        "vision_model": vision,
        "vision_optional": True,
        "estimate_download_gb": round(sum(MODELS[m][1] for m in
                                          [reasoning, vision] if m), 1),
        "note": ("GPU capability unknown; conservatively selected a CPU-capable model."
                 if gpu_vram_gb is None else
                 "Recommendation based on local RAM, NVIDIA VRAM and disk space."),
    }


def find_ollama_binary() -> Path | None:
    found = shutil.which("ollama")
    choices = [Path(found)] if found else []
    if sys.platform == "win32":
        home = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        choices.extend([home / "Programs" / "Ollama" / "ollama.exe",
                        home / "Ollama" / "ollama.exe"])
    return next((item for item in choices if item.is_file()), None)


def install_official_ollama(update) -> None:
    """Download official per-user installer, verify Authenticode, then execute.

    Do not silently execute or trust a mutable, unsigned installer. A failed
    signature causes hard failure, never a fallback to unsigned execution.
    """
    if sys.platform != "win32":
        raise RuntimeError("Automatic Ollama installation is supported on Windows only")
    with tempfile.TemporaryDirectory(prefix="piko-ollama-") as folder:
        target = Path(folder) / "OllamaSetup.exe"
        update("downloading-runtime", 0)
        req = urllib.request.Request(INSTALLER_URL, headers={"User-Agent": "Piko-Local-Setup/1"})
        total = 0
        with urllib.request.urlopen(req, timeout=60) as response, target.open("wb") as out:
            # One fixed official origin: forbid redirecting the executable
            # download to an unrelated host.
            final_url = response.geturl()
            from urllib.parse import urlsplit
            if urlsplit(final_url).scheme != "https" or urlsplit(final_url).hostname not in {
                "ollama.com", "github.com", "release-assets.githubusercontent.com",
                "objects.githubusercontent.com",
            }:
                raise RuntimeError("Installer redirected to an unapproved origin")
            estimated = int(response.headers.get("Content-Length", "0"))
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 3_000_000_000:
                    raise RuntimeError("Official installer exceeded safety size cap")
                out.write(chunk)
                update("downloading-runtime", round(total / estimated * 100)
                       if estimated else 0)
        update("verifying-signature", 0)
        check = (
            "$s = Get-AuthenticodeSignature -LiteralPath $env:PIKO_SETUP_EXE; "
            "if ($s.Status -ne 'Valid' -or $null -eq $s.SignerCertificate "
            "-or $s.SignerCertificate.Subject -notmatch 'Ollama') { exit 1 }"
        )
        env = {**os.environ, "PIKO_SETUP_EXE": str(target)}
        verified = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", check],
            env=env, timeout=120, capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if verified.returncode != 0:
            raise RuntimeError("Ollama installer Authenticode signature verification failed")
        update("installing-runtime", 0)
        installed = subprocess.run(
            [str(target), "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
            timeout=1800, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if installed.returncode != 0:
            raise RuntimeError("Official Ollama installer failed")
    if find_ollama_binary() is None:
        raise RuntimeError("Ollama installer finished but the CLI could not be located")


class SetupCoordinator:
    def __init__(self, provider: OllamaProvider, on_models_selected) -> None:
        self.provider = provider
        self.on_models_selected = on_models_selected
        self._task: asyncio.Task | None = None
        self.state = {"stage": "idle", "progress": 0, "error": None,
                      "reasoning": None, "vision": None}

    def status(self) -> dict:
        return {**self.state, "running": bool(self._task and not self._task.done()),
                "hardware": hardware_profile(),
                "ollama_installed": find_ollama_binary() is not None}

    def _update(self, stage: str, progress: int = 0) -> None:
        self.state.update(stage=stage, progress=progress)

    def start(self, reasoning: str, vision: str | None) -> None:
        if self._task is not None and not self._task.done():
            raise ValueError("Ollama setup already running")
        if reasoning not in MODELS or MODELS[reasoning][0] != "reasoning":
            raise ValueError("Choose an approved local reasoning model")
        if vision is not None and (vision not in MODELS or MODELS[vision][0] != "vision"):
            raise ValueError("Choose an approved local vision model or disable it")
        profile = hardware_profile()
        if profile["free_disk_gb"] < sum(MODELS[x][1] for x in (reasoning, vision) if x) + 4:
            raise ValueError("Not enough disk space for Ollama and the selected models")
        self.state = {"stage": "starting", "progress": 0, "error": None,
                      "reasoning": reasoning, "vision": vision}
        self._task = asyncio.create_task(self._configure(reasoning, vision))

    async def _ensure_service(self) -> None:
        if await check_service():
            return
        binary = find_ollama_binary()
        if binary is None:
            raise RuntimeError("Ollama CLI is unavailable after installation")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([str(binary), "serve"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434",
                              "OLLAMA_NO_CLOUD": "1"}, creationflags=flags)
        for _ in range(30):
            if await check_service():
                return
            await asyncio.sleep(1)
        raise RuntimeError("Local Ollama service did not start")

    async def _pull(self, model: str) -> None:
        self._update("downloading-model", 0)
        async with httpx.AsyncClient(base_url="http://127.0.0.1:11434",
                                     timeout=None, trust_env=False) as client:
            async with client.stream("POST", "/api/pull",
                                     json={"model": model, "stream": True}) as response:
                response.raise_for_status()
                completed = False
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    result = json.loads(line)
                    if result.get("error"):
                        raise RuntimeError("Ollama model pull failed")
                    if result.get("status") == "success":
                        completed = True
                    if result.get("total"):
                        self._update("downloading-model", min(
                            100, round(100 * result.get("completed", 0) / result["total"])))
                if not completed:
                    raise RuntimeError("Ollama model download ended without success")

    async def _configure(self, reasoning: str, vision: str | None) -> None:
        try:
            if not await check_service() and find_ollama_binary() is None:
                await asyncio.to_thread(install_official_ollama, self._update)
            self._update("starting-runtime", 0)
            await self._ensure_service()
            installed = {item["name"] for item in await self.provider.models()}
            for model in (reasoning, vision):
                if model and model not in installed:
                    self.state["current_model"] = model
                    await self._pull(model)
            self.provider.reasoning_model = reasoning
            self.provider.vision_model = vision
            self.on_models_selected(vision)
            self._update("ready", 100)
            self.state["error"] = None
        except Exception as exc:
            self.state["error"] = str(exc)[:260]
            self._update("failed", 0)
