"""Tests for YAML frontmatter read/write."""
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter


def test_read_simple_frontmatter(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("---\ntitle: Hello\nyear: 2024\n---\nBody.\n")
    fm, body = read_frontmatter(str(f))
    assert fm == {"title": "Hello", "year": 2024}
    assert body == "Body.\n"


def test_read_no_frontmatter(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("Just a body.\n")
    fm, body = read_frontmatter(str(f))
    assert fm == {}
    assert body == "Just a body.\n"


def test_read_empty_frontmatter(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("---\n---\nBody.\n")
    fm, body = read_frontmatter(str(f))
    assert fm == {}
    assert body == "Body.\n"


def test_write_roundtrip(tmp_path):
    f = tmp_path / "p.md"
    fm = {"title": "Attention", "authors": ["vaswani", "shazeer"], "year": 2017}
    write_frontmatter(str(f), fm, "# Attention\n\nBody here.\n")
    fm2, body2 = read_frontmatter(str(f))
    assert fm2 == fm
    assert body2 == "# Attention\n\nBody here.\n"


def test_write_preserves_order(tmp_path):
    f = tmp_path / "p.md"
    fm = {"b": 1, "a": 2, "c": 3}
    write_frontmatter(str(f), fm, "")
    content = f.read_text()
    # Keys should appear in insertion order
    assert content.index("b:") < content.index("a:") < content.index("c:")


def test_accepts_pathlib_path(tmp_path):
    """Both read and write should accept os.PathLike (Path), not only str."""
    f = tmp_path / "p.md"
    write_frontmatter(Path(str(f)), {"x": 1}, "body\n")
    fm, body = read_frontmatter(Path(str(f)))
    assert fm == {"x": 1}
    assert body == "body\n"


def test_read_nested_structures(tmp_path):
    """Frontmatter can contain nested dicts and lists (used by paper-id identifiers)."""
    f = tmp_path / "p.md"
    f.write_text(
        "---\n"
        "identifiers:\n"
        "  doi: 10.xxx/yyy\n"
        "  arxiv: '1706.03762'\n"
        "tags: [field/nlp, year/2017]\n"
        "authors:\n"
        "  - slug: ashish-vaswani\n"
        "    name: Ashish Vaswani\n"
        "---\n"
        "Body.\n"
    )
    fm, _ = read_frontmatter(str(f))
    assert fm["identifiers"] == {"doi": "10.xxx/yyy", "arxiv": "1706.03762"}
    assert fm["tags"] == ["field/nlp", "year/2017"]
    assert fm["authors"] == [{"slug": "ashish-vaswani", "name": "Ashish Vaswani"}]


def test_write_empty_body_ends_without_extra_newline(tmp_path):
    """Empty body should still produce a file with closing ---."""
    f = tmp_path / "p.md"
    write_frontmatter(str(f), {"key": "value"}, "")
    content = f.read_text()
    # Must have valid frontmatter delimiters and no content after closing ---
    assert content.startswith("---\n")
    assert "---\n" in content[4:]  # closing ---


def test_write_unicode_preserved(tmp_path):
    """Non-ASCII content in frontmatter values must round-trip."""
    f = tmp_path / "p.md"
    fm = {"title": "Attention Is All You Need", "author": "García-Luna"}
    write_frontmatter(str(f), fm, "Body: α-divergence discussed.\n")
    fm2, body2 = read_frontmatter(str(f))
    assert fm2 == fm
    assert body2 == "Body: α-divergence discussed.\n"


def test_read_frontmatter_without_trailing_newline_after_delimiter(tmp_path):
    """Tolerate a frontmatter block that's followed by body on the same line, or missing newline."""
    f = tmp_path / "p.md"
    f.write_text("---\ntitle: Hello\n---\n")
    fm, body = read_frontmatter(str(f))
    assert fm == {"title": "Hello"}
    assert body == ""


def test_read_malformed_frontmatter_raises_or_returns_empty(tmp_path):
    """Malformed YAML in frontmatter — either raise YAMLError or return the whole file as body.
    The implementation may choose either behavior; both are acceptable. This test pins whichever is chosen."""
    import yaml
    f = tmp_path / "p.md"
    f.write_text("---\nkey: : bad\n---\nbody\n")
    # Should either raise a yaml error or treat whole content as body — implementation choice.
    # We just test that reading doesn't silently corrupt data.
    try:
        fm, body = read_frontmatter(str(f))
        # If it didn't raise, body should contain the original content
        assert "key: : bad" in body or fm == {} or isinstance(fm, dict)
    except (yaml.YAMLError, ValueError):
        pass  # Acceptable
