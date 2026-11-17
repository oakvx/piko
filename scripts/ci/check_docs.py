"""Check local Markdown links without network access or extra dependencies."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]+\]\((?P<target><[^>\n]+>|[^)\s]+)")
HTML_LINK = re.compile(r"\b(?:href|src)\s*=\s*([\"'])(?P<target>.*?)\1")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def markdown_files(root: Path) -> list[Path]:
    files = set(root.glob("*.md"))
    for directory in ("docs", ".github"):
        folder = root / directory
        if folder.exists():
            files.update(folder.rglob("*.md"))
    return sorted(files)


def local_target(source: Path, raw: str, root: Path) -> Path | None:
    raw = raw.strip("<>")
    if raw.startswith(("#", "/", "//", "{")):
        return None
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    return (source.parent / unquote(parsed.path)).resolve()


def check_links(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    for source in markdown_files(root):
        text = HTML_COMMENT.sub("", source.read_text(encoding="utf-8"))
        fence: str | None = None
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith(("~~~", "```")):
                mark = stripped[:3]
                if fence is None:
                    fence = mark
                elif mark == fence:
                    fence = None
                continue
            if fence is not None:
                continue
            targets = [m.group("target") for m in MARKDOWN_LINK.finditer(line)]
            targets += [m.group("target") for m in HTML_LINK.finditer(line)]
            for raw in targets:
                path = local_target(source, raw, root)
                if path is None:
                    continue
                if not path.is_relative_to(root) or not path.exists():
                    rel = source.relative_to(root).as_posix()
                    errors.append(f"{rel}:{lineno}: broken local link: {raw}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = check_links(args.root)
    for error in errors:
        print(error)
    if errors:
        print(f"{len(errors)} broken local Markdown link(s)")
        return 1
    print(f"Markdown local links: OK ({len(markdown_files(args.root))} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
