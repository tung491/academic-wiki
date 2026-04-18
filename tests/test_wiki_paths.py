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


def test_find_wiki_rejects_directory_named_claude_md(tmp_path):
    """A directory (not file) named CLAUDE.md should NOT qualify."""
    fake = tmp_path / "fake"
    (fake / "wiki").mkdir(parents=True)
    (fake / "CLAUDE.md").mkdir()  # directory, not file
    assert find_active_wiki(str(fake)) is None


def test_list_wikis_rejects_directory_named_claude_md(tmp_path):
    """Same rule applies to list_wikis."""
    base = tmp_path / "03-Resources"
    fake = base / "fake"
    (fake / "wiki").mkdir(parents=True)
    (fake / "CLAUDE.md").mkdir()
    assert list_wikis(str(base)) == []


# ---------------------------------------------------------------------------
# find_all_extracts
# ---------------------------------------------------------------------------

from academic_wiki_lib.wiki_paths import find_all_extracts


def test_find_all_extracts_from_raw_extracts(tmp_wiki):
    """Finds standard extracts in raw/extracts/."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    extract = tmp_wiki / "raw/extracts/vaswani2017attention.md"
    write_frontmatter(str(extract), {"paper-id": "vaswani2017attention"}, "body")
    result = find_all_extracts(str(tmp_wiki))
    assert result == [("vaswani2017attention", str(extract))]


def test_find_all_extracts_from_clipper_dirs(tmp_wiki):
    """Finds clipper .md files in raw/papers/*/."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    clipper_dir = tmp_wiki / "raw/papers/Some_Paper_Dir"
    clipper_dir.mkdir(parents=True)
    clipper_md = clipper_dir / "Some_Paper.md"
    write_frontmatter(str(clipper_md), {"paper-id": "smith2020survey"}, "body")
    result = find_all_extracts(str(tmp_wiki))
    assert result == [("smith2020survey", str(clipper_md))]


def test_find_all_extracts_both_sources(tmp_wiki):
    """Merges both raw/extracts/ and raw/papers/*/ sources, sorted by paper-id."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    e1 = tmp_wiki / "raw/extracts/vaswani2017attention.md"
    write_frontmatter(str(e1), {"paper-id": "vaswani2017attention"}, "body")
    clipper_dir = tmp_wiki / "raw/papers/Some_Dir"
    clipper_dir.mkdir(parents=True)
    e2 = clipper_dir / "Paper.md"
    write_frontmatter(str(e2), {"paper-id": "chen2023wireless"}, "body")
    result = find_all_extracts(str(tmp_wiki))
    assert len(result) == 2
    assert result[0][0] == "chen2023wireless"
    assert result[1][0] == "vaswani2017attention"


def test_find_all_extracts_skips_no_paper_id(tmp_wiki):
    """Clipper .md without paper-id in frontmatter is skipped."""
    clipper_dir = tmp_wiki / "raw/papers/Unprocessed_Dir"
    clipper_dir.mkdir(parents=True)
    (clipper_dir / "Paper.md").write_text("---\ntitle: Something\n---\nbody")
    result = find_all_extracts(str(tmp_wiki))
    assert result == []


def test_find_all_extracts_skips_versions_yml(tmp_wiki):
    """*.versions.yml files in raw/extracts/ must not be treated as extracts."""
    (tmp_wiki / "raw/extracts/paper.versions.yml").write_text("- version: v1\n")
    result = find_all_extracts(str(tmp_wiki))
    assert result == []


def test_find_all_extracts_empty_wiki(tmp_wiki):
    result = find_all_extracts(str(tmp_wiki))
    assert result == []
