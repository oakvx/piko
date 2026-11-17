"""Regression tests for the dependency-free repository documentation checker."""

from pathlib import Path

from scripts.ci.check_docs import check_links, local_target, markdown_files


def test_checks_valid_local_links_and_ignores_external_urls(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "README.md").write_text(
        "[guide](docs/guide.md#intro) [website](https://example.org/a) "
        "[anchor](#install) ![badge](https://example.org/badge.svg)\n",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text(
        "# Intro\n[home](../README.md) <a href='../README.md'>Back</a>\n",
        encoding="utf-8",
    )
    assert len(markdown_files(tmp_path)) == 2
    assert check_links(tmp_path) == []


def test_detects_broken_links_with_file_and_line(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Readme\n[missing](docs/missing.md)\n", encoding="utf-8"
    )
    assert check_links(tmp_path) == ["README.md:2: broken local link: docs/missing.md"]


def test_ignores_fenced_examples_and_html_comments(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "<!-- [example](no-file.md) -->\n"
        "~~~md\n[example](no-file.md)\n~~~\n"
        "```html\n<img src='missing.svg'>\n```\n",
        encoding="utf-8",
    )
    assert check_links(tmp_path) == []


def test_url_encoded_spaces_and_directory_links(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a b.md").write_text("# OK\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "[space](docs/a%20b.md) [directory](docs/)\n", encoding="utf-8"
    )
    assert check_links(tmp_path) == []


def test_rejects_path_outside_repository(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[escape](../../escape.md)\n", encoding="utf-8")
    assert check_links(tmp_path) == ["README.md:1: broken local link: ../../escape.md"]


def test_skips_external_absolute_and_fragment_targets(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "x.md"
    for target in ("#section", "/site/root", "https://example.org", "mailto:a@example.org"):
        assert local_target(source, target, tmp_path) is None
