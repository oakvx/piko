"""Offline regression checks for deterministic three-ecosystem release inventory."""
from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/ci/generate_sbom.py"
spec = spec_from_file_location("piko_sbom", PATH)
sbom = module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(sbom)


def build_fixture(root: Path) -> None:
    python = root / "scripts/ci"
    python.mkdir(parents=True)
    (python / "backend-windows.lock").write_text(
        "# pinned Windows Python packages\n-e .\nfastapi==0.163.1\n"
        "pydantic-core==2.50.4\n", encoding="utf-8"
    )
    desktop = root / "apps/desktop"
    desktop.mkdir(parents=True)
    (desktop / "package-lock.json").write_text(json.dumps({
        "name": "piko-desktop", "version": "0.1.1", "lockfileVersion": 3,
        "packages": {
            "": {"name": "piko-desktop", "version": "0.1.1"},
            "node_modules/@scope/lib": {"version": "1.2.3", "license": "MIT"},
            "node_modules/other/node_modules/leaf": {"version": "4.5.6"},
        },
    }), encoding="utf-8")
    rust = desktop / "src-tauri"
    rust.mkdir()
    (rust / "Cargo.lock").write_text(
        'version = 3\n[[package]]\nname = "piko-desktop"\n'
        'version = "0.1.1"\n[[package]]\nname = "tauri"\n'
        'version = "2.9.5"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n',
        encoding="utf-8",
    )


def test_lock_inventory_is_reproducible_and_source_bound(tmp_path):
    build_fixture(tmp_path)
    sha = "f" * 40
    first = sbom.inventory(tmp_path, sha)
    assert first == sbom.inventory(tmp_path, sha)
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.6"
    assert first["metadata"]["properties"][0]["value"] == sha
    assert first["metadata"]["component"]["version"] == "0.1.1"
    assert {c["purl"] for c in first["components"]} == {
        "pkg:pypi/fastapi@0.163.1",
        "pkg:pypi/pydantic-core@2.50.4",
        "pkg:npm/%40scope%2Flib@1.2.3",
        "pkg:npm/leaf@4.5.6",
        "pkg:cargo/tauri@2.9.5",
    }
    assert all(c["properties"][0]["name"] == "piko:lockfile"
               for c in first["components"])
    assert sbom.inventory(tmp_path, "e" * 40)["metadata"] != first["metadata"]


def test_sbom_refuses_invalid_commit_or_unlocked_dependencies(tmp_path):
    build_fixture(tmp_path)
    with pytest.raises(ValueError, match="source commit"):
        sbom.inventory(tmp_path, "not-a-git-sha")
    rust = tmp_path / "apps/desktop/src-tauri/Cargo.lock"
    rust.write_text(rust.read_text().replace("registry+https://", "git+https://"))
    with pytest.raises(ValueError, match="Rust crate source"):
        sbom.inventory(tmp_path, "1" * 40)
    rust.write_text(rust.read_text().replace("git+https://", "registry+https://"))
    python = tmp_path / "scripts/ci/backend-windows.lock"
    python.write_text(python.read_text() + "not-locked>=1.0\n")
    with pytest.raises(ValueError, match="Unrecognized Python lock"):
        sbom.inventory(tmp_path, "1" * 40)


def test_actual_repository_lock_inventory_has_all_three_ecosystems():
    manifest = sbom.inventory(ROOT, "a" * 40)
    refs = {c["purl"].split("/", 1)[0] for c in manifest["components"]}
    assert refs == {"pkg:pypi", "pkg:npm", "pkg:cargo"}
    assert len(manifest["components"]) > 200
    assert any(c["name"] == "fastapi" for c in manifest["components"])
    assert any(c["name"] == "tauri" for c in manifest["components"])
