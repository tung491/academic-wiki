"""Tests for wiki templates."""
from academic_wiki_lib.templates import (
    INDEX_MD,
    LOG_MD,
    GITIGNORE,
    claude_md,
    qmd_yml,
    all_subdirs,
)


def test_all_subdirs_matches_spec():
    """Must match the 16 subdirectories in spec §2.2."""
    expected = {
        "raw/papers", "raw/extracts", "raw/bib", "raw/figures", "raw/notes",
        "wiki/papers", "wiki/concepts", "wiki/methods", "wiki/open-problems",
        "wiki/claims", "wiki/results", "wiki/authors", "wiki/venues", "wiki/queries",
        "outputs/reports", "outputs/bib",
    }
    assert set(all_subdirs()) == expected


def test_all_subdirs_returns_sixteen():
    assert len(all_subdirs()) == 16


def test_claude_md_contains_expected_section_headers_skeleton():
    """Task 1.9 claude_md is a skeleton with section headers — full content in Task 1.10."""
    doc = claude_md("academic")
    assert "# academic Wiki Schema" in doc
    assert "## Directory Layout" in doc
    assert "## Identity Model" in doc
    assert "## Entity Types" in doc
    assert "## Tag Taxonomy" in doc
    assert "## Slug Generation" in doc
    assert "## Update Conflict Policy" in doc
    assert "## Lockfile Semantics" in doc


def test_claude_md_substitutes_name():
    """Name substitution: {{NAME}} markers should be replaced everywhere."""
    doc = claude_md("my-topic")
    assert "# my-topic Wiki Schema" in doc
    assert "{{NAME}}" not in doc


def test_index_md_contains_wiki_index_header():
    assert "Wiki Index" in INDEX_MD


def test_log_md_contains_wiki_log_header():
    assert "Wiki Log" in LOG_MD


def test_index_md_is_name_templated():
    """INDEX_MD uses {name} for .format(name=...) substitution."""
    formatted = INDEX_MD.format(name="academic")
    assert "academic Wiki Index" in formatted


def test_log_md_is_name_templated():
    formatted = LOG_MD.format(name="academic")
    assert "academic Wiki Log" in formatted


def test_gitignore_excludes_lock_and_sqlite():
    assert ".lock" in GITIGNORE
    assert "*.sqlite" in GITIGNORE


def test_gitignore_excludes_DS_Store():
    assert ".DS_Store" in GITIGNORE


def test_qmd_yml_is_parameterized():
    y = qmd_yml("academic")
    assert "collections:" in y
    assert "academic:" in y
    assert "./wiki" in y
    assert "**/*.md" in y


def test_qmd_yml_different_names():
    y1 = qmd_yml("academic")
    y2 = qmd_yml("other-topic")
    assert "academic" in y1
    assert "other-topic" in y2


def test_claude_md_has_no_to_be_filled_markers():
    """Task 1.10 must fill in all spec content — no placeholders remain."""
    doc = claude_md("academic")
    assert "<TO BE FILLED" not in doc
    assert "TO BE FILLED" not in doc  # Catch variant phrasings


def test_claude_md_is_substantial():
    """After Task 1.10 fills in all sections, CLAUDE.md should be >=500 lines."""
    doc = claude_md("academic")
    assert doc.count("\n") >= 500, f"CLAUDE.md only has {doc.count(chr(10))} lines"


def test_claude_md_contains_key_spec_content():
    """Spot checks that specific content from key spec sections is present."""
    doc = claude_md("academic")
    # From §3.1 paper schema
    assert "paper-id" in doc
    assert "citation-key" in doc
    assert "identifiers:" in doc
    # From §3.5 slug generation
    assert "Unicode NFKD normalize" in doc or "NFKD" in doc
    # From §3.7 raw-side metadata
    assert "source-sha" in doc
    # From §4 tag taxonomy
    assert "field/" in doc
    assert "subfield/" in doc
    # From §5.2 ingest
    assert "arXiv" in doc
    # From §5.7 snapshot
    assert "snapshot/" in doc
    # From §8.1 lockfile
    assert ".lock" in doc
