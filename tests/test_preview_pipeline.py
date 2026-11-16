"""Offline checks for the continuous Windows installer release workflow."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_preview_gating_and_release_files():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    assert "github.run_id" in workflow["concurrency"]["group"]
    assert "github.event.pull_request.number" in workflow["concurrency"]["group"]
    assert "github.event_name == 'pull_request'" in workflow["concurrency"]["cancel-in-progress"]
    assert jobs["windows-installer"]["runs-on"] == "windows-latest"
    assert jobs["windows-installer-smoke"]["runs-on"] == "windows-latest"
    assert jobs["windows-installer-smoke"]["needs"] == ["windows-installer"]
    assert jobs["publish-preview"]["needs"] == ["windows-installer", "windows-installer-smoke"]
    installer_smoke_steps = "\n".join(
        step.get("run", "") for step in jobs["windows-installer-smoke"]["steps"]
    )
    assert "smoke-installer.ps1" in installer_smoke_steps
    assert "checksum mismatch" in installer_smoke_steps
    assert jobs["windows-installer"]["needs"] == ["python", "frontend", "python-dependency-audit", "rust-dependency-audit", "windows-gui-smoke"]
    assert "rust-dependency-audit" in jobs
    rust_scan_steps = jobs["rust-dependency-audit"]["steps"]
    rust_scan = "\n".join(step.get("run", "") for step in rust_scan_steps)
    assert "cargo install --locked --version 0.23.0 cargo-audit" in rust_scan
    assert "cargo audit --file apps/desktop/src-tauri/Cargo.lock" in rust_scan
    assert not any("rustsec/audit-check" in step.get("uses", "") for step in rust_scan_steps)
    assert jobs["rust-dependency-audit"].get("permissions", {}).get("checks") != "write"
    assert "npm ci" in "\n".join(step.get("run", "") for step in jobs["frontend"]["steps"])
    assert "cargo metadata --locked" in "\n".join(
        step.get("run", "") for step in jobs["windows-installer"]["steps"])
    assert "pull_request" in jobs["publish-preview"]["if"]
    assert "refs/heads/main" in jobs["publish-preview"]["if"]
    assert jobs["publish-preview"]["permissions"]["contents"] == "write"
    script = "\n".join(step.get("run", "") for step in jobs["publish-preview"]["steps"])
    assert "sha256sum --check" in script
    assert "--prerelease" in script
    assert "--target \"$SHA\"" in script
    assert "--clobber" in script
    assert "--latest=false" in script


def test_sidecar_included_in_tauri_installer():
    config = json.loads((ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text())
    assert config["bundle"]["targets"] == ["nsis"]
    assert config["bundle"]["externalBin"] == ["binaries/piko-agent"]
    assert "http://127.0.0.1:*" in config["app"]["security"]["csp"]
    assert "PIKO_CONTROL_TOKEN" in (ROOT / "apps/desktop/src-tauri/src/lib.rs").read_text()


def test_ci_version_stamping(tmp_path, monkeypatch):
    path = ROOT / "scripts/ci/version.py"
    spec = spec_from_file_location("preview_version", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    desktop = tmp_path / "apps/desktop"
    desktop.mkdir(parents=True)
    (desktop / "package.json").write_text('{"version":"0.1.0-alpha.1"}')
    tauri = desktop / "src-tauri"
    tauri.mkdir()
    (tauri / "tauri.conf.json").write_text('{"version":"0.1.0-alpha.1"}')
    (tauri / "Cargo.toml").write_text('[package]\nversion = "0.1.0-alpha.1"\n')
    assert module.stamp(134) == "0.1.134"
    assert json.loads((desktop / "package.json").read_text())["version"] == "0.1.134"
    assert json.loads((tauri / "tauri.conf.json").read_text())["version"] == "0.1.134"
    assert re.search(r'version = "0.1.134"', (tauri / "Cargo.toml").read_text())
    with pytest.raises(ValueError):
        module.stamp(65536)


def test_ci_version_stamping_keeps_dependency_locks_synchronized(tmp_path, monkeypatch):
    path = ROOT / "scripts/ci/version.py"
    spec = spec_from_file_location("preview_version_locked", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    desktop = tmp_path / "apps/desktop"
    tauri = desktop / "src-tauri"
    tauri.mkdir(parents=True)
    (desktop / "package.json").write_text('{"version":"0.1.0-alpha.1"}')
    (desktop / "package-lock.json").write_text(json.dumps({
        "version": "0.1.0-alpha.1",
        "packages": {"": {"version": "0.1.0-alpha.1"}},
    }))
    (tauri / "tauri.conf.json").write_text('{"version":"0.1.0-alpha.1"}')
    (tauri / "Cargo.toml").write_text('[package]\nversion = "0.1.0-alpha.1"\n')
    (tauri / "Cargo.lock").write_text(
        '[[package]]\nname = "piko-desktop"\nversion = "0.1.0-alpha.1"\n'
    )
    assert module.stamp(321) == "0.1.321"
    npm = json.loads((desktop / "package-lock.json").read_text())
    assert npm["version"] == npm["packages"][""]["version"] == "0.1.321"
    assert 'version = "0.1.321"' in (tauri / "Cargo.lock").read_text()


def test_ci_github_actions_are_immutable_pins():
    """Prevent a moving third-party action tag from changing release provenance."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            uses = step.get("uses")
            if uses:
                assert re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[a-f0-9]{40}", uses), (
                    f"Unpinned GitHub Action: {uses}"
                )
