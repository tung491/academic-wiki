"""Tests for wiki templates."""
from academic_wiki_lib.templates import (
    INDEX_MD,
    LOG_MD,
    GITIGNORE,
    claude_md,
    qmd_yml,
    all_subdirs,
    guess_venue_type,
    venue_md_stub,
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
    assert "citation-key" not in doc  # dropped — paper-id now serves as BibTeX @key
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


def test_claude_md_uses_literal_plugin_name_not_templated():
    """Command invocations use the fixed plugin name `academic-wiki`, not the wiki name."""
    # Render with a wiki name that would obviously be wrong if used as plugin name
    doc = claude_md("physics")
    # Plugin invocations should use academic-wiki literal
    assert "/academic-wiki:wiki" in doc
    # Should NEVER contain the wiki name as plugin name
    assert "/physics-wiki:wiki" not in doc
    assert "/physics:wiki" not in doc


def test_claude_md_contains_init_section():
    """§5.1 init rules must be present."""
    doc = claude_md("academic")
    # The init section should appear
    assert "Init Rules" in doc or "init [<name>]" in doc or "Scaffolds a new wiki" in doc


def test_claude_md_contains_remove_section():
    """§5.8 remove rules must be present."""
    doc = claude_md("academic")
    assert "Remove Rules" in doc or "remove <name>" in doc or "Deletes a wiki" in doc


def test_claude_md_line_count_after_additions():
    """CLAUDE.md should be substantial after all sections are present."""
    doc = claude_md("academic")
    # After citation-key removal and Wave terminology cleanup, expected ≥550 lines.
    assert doc.count("\n") >= 550, f"expected ≥550 lines, got {doc.count(chr(10))}"


def test_guess_venue_type_journal_keywords():
    assert guess_venue_type("IEEE Transactions on Networking") == "journal"
    assert guess_venue_type("IEEE Communications Surveys & Tutorials") == "journal"
    assert guess_venue_type("Nature Machine Intelligence") == "journal"
    assert guess_venue_type("Computer Networks") == "journal"
    assert guess_venue_type("IEEE Communications Letters") == "journal"


def test_guess_venue_type_conference_keywords():
    assert guess_venue_type("IEEE International Conference on Communications") == "conference"
    assert guess_venue_type("ACM Symposium on Theory of Computing") == "conference"
    assert guess_venue_type("Proceedings of NeurIPS 2024") == "conference"


def test_guess_venue_type_workshop():
    assert guess_venue_type("NeurIPS 2024 Workshop on Foundation Models") == "workshop"


def test_guess_venue_type_preprint_server():
    assert guess_venue_type("arXiv") == "preprint-server"
    assert guess_venue_type("arXiv preprint") == "preprint-server"
    assert guess_venue_type("bioRxiv") == "preprint-server"


def test_guess_venue_type_default_is_journal():
    assert guess_venue_type("Unknown Publication") == "journal"


def test_guess_venue_type_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        guess_venue_type("")
    with pytest.raises(ValueError):
        guess_venue_type("   ")


def test_guess_venue_type_workshop_beats_conference():
    """Workshop keyword must win even when the name also contains conference keywords."""
    assert guess_venue_type("ICML Workshop on Robustness") == "workshop"
    assert guess_venue_type("NeurIPS Workshop co-located with the Conference") == "workshop"


def test_venue_md_stub_has_all_required_fields():
    md = venue_md_stub(
        slug="ieee-communications-surveys-tutorials",
        name="IEEE Communications Surveys & Tutorials",
        venue_type="journal",
        paper_ids=["gao2026agentic"],
        field_tags=["field/wireless-communications"],
        today="2026-04-18",
    )
    assert "type: venue" in md
    assert "name: \"IEEE Communications Surveys & Tutorials\"" in md
    assert "slug: ieee-communications-surveys-tutorials" in md
    assert "venue-type: journal" in md
    assert "created: 2026-04-18" in md
    assert "updated: 2026-04-18" in md
    assert "- gao2026agentic" in md
    assert "- field/wireless-communications" in md


def test_venue_md_stub_multiple_papers_and_fields():
    md = venue_md_stub(
        slug="neurips",
        name="Conference on Neural Information Processing Systems",
        venue_type="conference",
        paper_ids=["vaswani2017attention", "bahdanau2014neural"],
        field_tags=["field/nlp", "field/ml"],
        today="2026-04-18",
    )
    assert "- vaswani2017attention" in md
    assert "- bahdanau2014neural" in md
    assert "- field/nlp" in md
    assert "- field/ml" in md


def test_venue_md_stub_body_has_frontmatter_delimiters():
    md = venue_md_stub(
        slug="x", name="X", venue_type="journal",
        paper_ids=["a2024b"], field_tags=["field/x"], today="2026-04-18",
    )
    assert md.startswith("---\n")
    assert md.count("---\n") >= 2


def test_venue_md_stub_escapes_double_quotes_in_name():
    md = venue_md_stub(
        slug="s",
        name='The "Best" Journal',
        venue_type="journal",
        paper_ids=["x2024y"],
        field_tags=["field/x"],
        today="2026-04-18",
    )
    assert 'name: "The \\"Best\\" Journal"' in md


def test_venue_md_stub_empty_lists_render_as_square_brackets():
    md = venue_md_stub(
        slug="empty-venue",
        name="Empty Venue",
        venue_type="journal",
        paper_ids=[],
        field_tags=[],
        today="2026-04-18",
    )
    # Both papers: and tags: should have the []-placeholder line, so "  []" appears ≥2 times
    assert md.count("  []") == 2
    # And neither list should render as null
    assert "papers: null" not in md
    assert "tags: null" not in md
