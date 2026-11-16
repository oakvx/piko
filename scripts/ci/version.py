"""Stamp a monotonic CI preview version into the installer metadata.

This deliberately changes only CI working-tree files, never the release branch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def stamp(run_number: int) -> str:
    if not 1 <= run_number <= 65535:
        raise ValueError("CI run number must fit the Windows installer version field")
    version = f"0.1.{run_number}"
    package_path = ROOT / "apps/desktop/package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["version"] = version
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

    # npm ci requires the package version in the lockfile to match the
    # generated CI version; only the root package metadata is changed.
    npm_lock_path = ROOT / "apps/desktop/package-lock.json"
    if npm_lock_path.is_file():
        npm_lock = json.loads(npm_lock_path.read_text(encoding="utf-8"))
        npm_lock["version"] = version
        npm_lock["packages"][""]["version"] = version
        npm_lock_path.write_text(json.dumps(npm_lock, indent=2) + "\n", encoding="utf-8")

    config_path = ROOT / "apps/desktop/src-tauri/tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["version"] = version
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    cargo_path = ROOT / "apps/desktop/src-tauri/Cargo.toml"
    cargo = cargo_path.read_text(encoding="utf-8")
    cargo, count = re.subn(r'(?m)^(version\s*=\s*)"[^"]+"', rf'\g<1>"{version}"', cargo, count=1)
    if count != 1:
        raise ValueError("Cargo package version not found")
    cargo_path.write_text(cargo, encoding="utf-8")

    cargo_lock_path = ROOT / "apps/desktop/src-tauri/Cargo.lock"
    if cargo_lock_path.is_file():
        locked = cargo_lock_path.read_text(encoding="utf-8")
        expression = (r'(?m)^(name = "piko-desktop"\\nversion = )"[^"]+"')
        # This local package entry is the only Cargo.lock version changed.
        locked, count = re.subn(expression, lambda m: m.group(1) + f'"{version}"',
                                locked, count=1)
        if count != 1:
            raise ValueError("Cargo.lock local piko-desktop package entry not found")
        cargo_lock_path.write_text(locked, encoding="utf-8")
    return version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_number", type=int)
    args = parser.parse_args()
    print(stamp(args.run_number))


if __name__ == "__main__":
    main()
