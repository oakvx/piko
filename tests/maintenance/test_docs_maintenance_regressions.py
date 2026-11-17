"""Offline documentation checks must not follow external links or hidden examples."""

from scripts.ci.check_docs import check_links


def page(root, text, filename="README.md"):
    target = root / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_accept_valid_local_document_reference(tmp_path):
    page(tmp_path, "# Guide")
    page(tmp_path, "[Guide](docs/guide.md)")
    page(tmp_path, "# Detail", filename="docs/guide.md")
    assert check_links(tmp_path) == []


def test_accept_valid_parent_directory_reference(tmp_path):
    page(tmp_path, "[Home](../README.md)", filename="docs/guide.md")
    page(tmp_path, "# Home")
    assert check_links(tmp_path) == []


def test_ignore_external_https_dependency(tmp_path):
    page(tmp_path, "[External](https://example.org/guide)")
    assert check_links(tmp_path) == []


def test_ignore_mailto_documentation_reference(tmp_path):
    page(tmp_path, "[Contact](mailto:maintainer@example.org)")
    assert check_links(tmp_path) == []


def test_ignore_fragment_only_navigation_reference(tmp_path):
    page(tmp_path, "# Setup\n[Setup](#setup)\n")
    assert check_links(tmp_path) == []
