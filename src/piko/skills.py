"""Locally stored Skill drafts: explicit review, no arbitrary script execution."""
from __future__ import annotations

import json
import re
from pathlib import Path

from piko.contracts import Plan


class SkillError(ValueError):
    pass


class SkillLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _folder(self, slug: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
            raise SkillError("Skill slug must contain lowercase letters, digits, and hyphens")
        path = self.root / slug
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise SkillError("Invalid skill directory")
        return path

    def save_draft(self, slug: str, description: str, app_executable: str,
                   plan: Plan) -> Path:
        folder = self._folder(slug)
        if folder.exists():
            raise SkillError("Skill exists. Revision of established Skills requires review")
        folder.mkdir(mode=0o700)
        metadata = {"name": slug, "description": description,
                    "version": "0.1.0", "status": "draft", "executable": app_executable,
                    "actions": len(plan.actions), "requires_approval": True}
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (folder / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        (folder / "SKILL.md").write_text(
            f"# {slug}\n\n{description}\n\n## Status\nDRAFT — NOT VERIFIED. "
            "Require explicit execution approval and a fresh permission grant.\n\n"
            f"## Environment\n{app_executable}\n\n"
            "## Preconditions\nApplication is active, UIA targets are present, and user consent is valid.\n\n"
            "## Procedure\n" + "\n".join(
                f"{i}. {action.kind.value}: {action.automation_id or 'application'}, "
                f"verify {action.expected.automation_id}.{action.expected.property}"
                for i, action in enumerate(plan.actions, 1)) +
            "\n\n## Verification\nOnly observable UIA checks count as verification.\n\n"
            "## Recovery\nStop on unexpected UI changes; request user review.\n\n"
            "## Safety\nNo automatic script execution, privilege elevation, or secret collection.\n",
            encoding="utf-8")
        return folder

    def list_skills(self) -> list[dict]:
        results = []
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir() or folder.is_symlink():
                continue
            metadata = folder / "metadata.json"
            if metadata.is_file() and not metadata.is_symlink():
                try:
                    results.append(json.loads(metadata.read_text(encoding="utf-8")))
                except (ValueError, OSError):
                    continue
        return results

    def load_plan(self, slug: str) -> tuple[str, Plan]:
        folder = self._folder(slug)
        files = [folder / "metadata.json", folder / "plan.json"]
        if not all(p.is_file() and not p.is_symlink() for p in files):
            raise SkillError("Skill metadata or plan missing")
        metadata = json.loads(files[0].read_text(encoding="utf-8"))
        plan = Plan.model_validate_json(files[1].read_text(encoding="utf-8"))
        return metadata["executable"], plan
