"""Locally stored Skill drafts: explicit review, no arbitrary script execution."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
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
                    "version": "0.1.0", "revision": 1, "status": "draft", "executable": app_executable,
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

    def revise_draft(self, slug: str, description: str, plan: Plan) -> dict:
        """Archive the previous revision; verified Skills cannot be overwritten."""
        folder = self._folder(slug)
        metadata_path = folder / "metadata.json"
        plan_path = folder / "plan.json"
        markdown_path = folder / "SKILL.md"
        if not all(p.is_file() and not p.is_symlink()
                   for p in (metadata_path, plan_path, markdown_path)):
            raise SkillError("Invalid Skill files")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("status") != "draft":
            raise SkillError("A verified Skill cannot be modified in place")
        if not description.strip() or len(description) > 500:
            raise SkillError("Skill description must be 1–500 characters")
        # Strict typed schema rejects shell commands, extraneous fields, and
        # unsupported actions even if plan was loaded from a third-party file.
        checked = Plan.model_validate(plan)
        revision = int(metadata.get("revision", 1))
        backup = folder / "revisions" / f"revision-{revision}"
        if backup.exists() or backup.is_symlink():
            raise SkillError("Revision archive already exists")
        backup.mkdir(parents=True)
        for source in (metadata_path, plan_path, markdown_path):
            shutil.copy2(source, backup / source.name)
        metadata["revision"] = revision + 1
        metadata["version"] = f"0.1.{revision}"
        metadata["actions"] = len(checked.actions)
        metadata["description"] = description.strip()
        # Keep text documentation aligned with the typed executable plan.
        # Markdown is never used as an execution source.
        doc = (
            f"# {slug}\n\n{description.strip()}\n\n"
            "## Status\nDRAFT — NOT VERIFIED. Always require fresh permissions "
            "and review before executing.\n\n## Preconditions\n"
            f"Foreground application: {metadata['executable']}\n\n## Procedure\n"
            + "\n".join(
                f"{i}. {action.kind.value}: {action.automation_id or 'application'}; "
                f"expect {action.expected.automation_id}.{action.expected.property}"
                for i, action in enumerate(checked.actions, 1)
            )
            + "\n\n## Safety\nNo arbitrary command execution.\n"
        )
        for target, content in (
            (plan_path, checked.model_dump_json(indent=2)),
            (metadata_path, json.dumps(metadata, indent=2)),
            (markdown_path, doc),
        ):
            staged = folder / (target.name + ".pending")
            staged.write_text(content, encoding="utf-8")
            staged.replace(target)
        return metadata

    def record_run(self, slug: str, session_id: str, succeeded: bool) -> None:
        folder = self._folder(slug)
        self.load_plan(slug)
        path = folder / "history.json"
        if path.is_symlink():
            raise SkillError("Unsafe Skill history link")
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(history, list):
            raise SkillError("Corrupt Skill history")
        history.append({
            "session_id": session_id,
            "completed": bool(succeeded),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Successful session is not proof of generalization",
        })
        staged = folder / "history.pending"
        staged.write_text(json.dumps(history[-250:], indent=2), encoding="utf-8")
        staged.replace(path)

    def history(self, slug: str) -> list[dict]:
        folder = self._folder(slug)
        self.load_plan(slug)
        path = folder / "history.json"
        if path.is_symlink():
            raise SkillError("Unsafe Skill history link")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def load_plan(self, slug: str) -> tuple[str, Plan]:
        folder = self._folder(slug)
        files = [folder / "metadata.json", folder / "plan.json"]
        if not all(p.is_file() and not p.is_symlink() for p in files):
            raise SkillError("Skill metadata or plan missing")
        metadata = json.loads(files[0].read_text(encoding="utf-8"))
        plan = Plan.model_validate_json(files[1].read_text(encoding="utf-8"))
        return metadata["executable"], plan
