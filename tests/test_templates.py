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
