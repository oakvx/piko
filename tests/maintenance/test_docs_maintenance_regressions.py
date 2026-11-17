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


def test_decode_percent_encoded_local_target(tmp_path):
    page(tmp_path, "[Read](docs/a%20b.md)")
    page(tmp_path, "# Read", filename="docs/a b.md")
    assert check_links(tmp_path) == []


def test_detect_broken_readme_reference(tmp_path):
    page(tmp_path, "[Guide](docs/nope.md)")
    assert check_links(tmp_path) == ["README.md:1: broken local link: docs/nope.md"]


def test_detect_missing_html_image_resource(tmp_path):
    page(tmp_path, '<img src="docs/missing.png">')
    assert check_links(tmp_path) == ["README.md:1: broken local link: docs/missing.png"]


def test_ignore_missing_resource_in_fenced_code(tmp_path):
    fence = chr(96) * 3
    page(tmp_path, fence + "md\n[example](missing.md)\n" + fence + "\n")
    assert check_links(tmp_path) == []
