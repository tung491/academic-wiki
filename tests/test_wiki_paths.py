"""Tests for wiki root detection."""
from pathlib import Path

from academic_wiki_lib.wiki_paths import find_active_wiki, list_wikis


def test_find_wiki_from_within(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("")
    deep = wiki / "raw" / "papers"
    deep.mkdir(parents=True)
    assert find_active_wiki(str(deep)) == str(wiki)


def test_find_wiki_at_root(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("")
    assert find_active_wiki(str(wiki)) == str(wiki)


def test_find_wiki_from_root_returns_none(tmp_path):
    """No wiki markers anywhere in the tree."""
    assert find_active_wiki(str(tmp_path)) is None


def test_find_wiki_requires_both_claude_md_and_wiki_dir(tmp_path):
    """A directory with CLAUDE.md but no wiki/ subfolder should NOT be detected."""
    (tmp_path / "CLAUDE.md").write_text("")
    # No wiki/ subfolder
    assert find_active_wiki(str(tmp_path)) is None

    # And the converse: wiki/ but no CLAUDE.md
    wiki2 = tmp_path / "wiki2"
    (wiki2 / "wiki").mkdir(parents=True)
    assert find_active_wiki(str(wiki2)) is None


def test_find_wiki_accepts_pathlib_path(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("")
    # Pass Path, not str
    result = find_active_wiki(Path(str(wiki)))
    assert result == str(wiki)


def test_find_wiki_returns_closest_ancestor(tmp_path):
    """If nested wikis exist (unusual), the closest ancestor wins."""
    outer = tmp_path / "outer"
    (outer / "wiki").mkdir(parents=True)
    (outer / "CLAUDE.md").write_text("")
    inner = outer / "subdir" / "inner"
    (inner / "wiki").mkdir(parents=True)
    (inner / "CLAUDE.md").write_text("")
    # From a file deep inside inner, inner should be found (not outer)
    deep = inner / "raw" / "papers"
    deep.mkdir(parents=True)
    assert find_active_wiki(str(deep)) == str(inner)


def test_list_wikis(tmp_path):
    base = tmp_path / "03-Resources"
    for name in ["academic", "other", "not-a-wiki"]:
        d = base / name
        d.mkdir(parents=True)
    for name in ["academic", "other"]:
        (base / name / "wiki").mkdir()
        (base / name / "CLAUDE.md").write_text("")
    # not-a-wiki has neither CLAUDE.md nor wiki/
    wikis = list_wikis(str(base))
    assert set(wikis) == {"academic", "other"}


def test_list_wikis_empty_base(tmp_path):
    """list_wikis on an empty (or non-existent) base directory returns []."""
    assert list_wikis(str(tmp_path / "does-not-exist")) == []
    assert list_wikis(str(tmp_path)) == []


def test_list_wikis_returns_sorted(tmp_path):
    """Result is sorted alphabetically for deterministic output."""
    base = tmp_path / "03-Resources"
    for name in ["zed", "alpha", "mid"]:
        d = base / name
        (d / "wiki").mkdir(parents=True)
        (d / "CLAUDE.md").write_text("")
    wikis = list_wikis(str(base))
    assert wikis == ["alpha", "mid", "zed"]


def test_list_wikis_accepts_pathlib_path(tmp_path):
    """list_wikis should accept Path as well as str."""
    base = tmp_path / "03-Resources"
    (base / "academic" / "wiki").mkdir(parents=True)
    (base / "academic" / "CLAUDE.md").write_text("")
    from pathlib import Path
    assert list_wikis(Path(str(base))) == ["academic"]
