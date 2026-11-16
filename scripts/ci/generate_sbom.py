"""Reproducible CycloneDX inventory of the three Piko release input locks.

No dependency resolution, network access or executable invocation. This is a
lockfile-derived dependency inventory, NOT a completed license compliance
assessment or a substitute for a vulnerability audit.
"""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def inventory(root: Path, sha: str) -> dict:
    if not SHA.fullmatch(sha):
        raise ValueError("Provide a lowercase 40-character source commit SHA")
    components: dict[str, dict] = {}

    def add(ecosystem: str, name: str, version: str, source: str,
            license_label: str | None = None) -> None:
        if not name or not version:
            raise ValueError("Missing locked dependency name or version")
        purl = f"pkg:{ecosystem}/{quote(name, safe='')}@{quote(version, safe='')}"
        item = {
            "type": "library", "name": name, "version": version,
            "purl": purl, "bom-ref": purl,
            "properties": [{"name": "piko:lockfile", "value": source}],
        }
        if license_label:
            item["properties"].append(
                {"name": "piko:reported-license", "value": license_label}
            )
        if purl in components and components[purl] != item:
            raise ValueError(f"Contradictory locked components: {purl}")
        components[purl] = item

    python_lock = root / "scripts/ci/backend-windows.lock"
    for raw in python_lock.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-e "):
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise ValueError(f"Unrecognized Python lock entry: {line}")
        add("pypi", match.group(1).lower().replace("_", "-"), match.group(2),
            "scripts/ci/backend-windows.lock")

    npm = json.loads((root / "apps/desktop/package-lock.json").read_text(encoding="utf-8"))
    if npm.get("lockfileVersion") != 3:
        raise ValueError("Expected npm lockfile version 3")
    for path, entry in npm["packages"].items():
        if not path:
            continue  # The first-party application is metadata, not its own dependency.
        if "node_modules/" not in path:
            raise ValueError(f"Unexpected npm package path: {path}")
        name = path.rsplit("node_modules/", 1)[1]
        version = entry.get("version")
        if not isinstance(version, str):
            raise ValueError(f"Unversioned npm package: {path}")
        add("npm", name, version, "apps/desktop/package-lock.json",
            entry.get("license") if isinstance(entry.get("license"), str) else None)

    cargo = tomllib.loads(
        (root / "apps/desktop/src-tauri/Cargo.lock").read_text(encoding="utf-8")
    )
    for package in cargo["package"]:
        if "source" not in package:
            continue  # The local piko-desktop crate is part of the application.
        if not package["source"].startswith("registry+"):
            raise ValueError(f"Unexpected Rust crate source: {package['source']}")
        add("cargo", package["name"], package["version"],
            "apps/desktop/src-tauri/Cargo.lock")

    if not components:
        raise ValueError("No locked dependencies found")
    result = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "piko",
                          "version": npm["version"]},
            "properties": [
                {"name": "piko:source:commit", "value": sha},
                {"name": "piko:inventory:scope",
                 "value": "npm and Cargo locked source graph; Windows Python pinned versions"},
                {"name": "piko:license-review", "value": "incomplete"},
            ],
        },
        "components": sorted(components.values(), key=lambda x: x["purl"]),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true",
                        help="Verify existing output matches exact locked inputs")
    args = parser.parse_args()
    formatted = json.dumps(inventory(ROOT, args.source_sha),
                           indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != formatted:
            raise SystemExit("SBOM does not reproduce exact source SHA + lockfile inputs")
        print(f"Verified reproducible SBOM: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted, encoding="utf-8")
        print(f"Created source-locked SBOM: {args.output}")


if __name__ == "__main__":
    main()
