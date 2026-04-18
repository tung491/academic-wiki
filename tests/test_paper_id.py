"""Tests for paper-id generation and dedup logic."""
import pytest

from academic_wiki_lib.paper_id import (
    generate_paper_id,
    normalize_identifier,
    find_existing_paper_by_identifiers,
    resolve_collision,
)


def test_basic_paper_id():
    assert generate_paper_id("Vaswani", 2017, "Attention Is All You Need") == "vaswani2017attention"


def test_stop_word_in_title_dropped():
    assert generate_paper_id("Smith", 2020, "The Future of AI") == "smith2020future"


def test_ascii_fold_in_lastname():
    assert generate_paper_id("García", 2024, "Survey of RSMA") == "garcia2024survey"


def test_pure_numeric_first_word_skipped():
    """A pure numeric word is skipped (e.g., '1000' as a leading number)."""
    assert generate_paper_id("Chen", 2023, "1000 Genomes Project") == "chen2023genomes"


def test_alphanumeric_first_word_kept():
    """A leading digit-alpha compound like '5G' is kept — it's the distinguishing term."""
    assert generate_paper_id("Chen", 2023, "5G Networks") == "chen20235g"
    assert generate_paper_id("Smith", 2024, "3D Printing Trends") == "smith20243d"


def test_multiple_stop_words_skipped():
    """Spec §5.2: skip stop words a/an/the and numerals until finding first meaningful word."""
    assert generate_paper_id("Jones", 2022, "A the of Framework for Deep Learning") == "jones2022framework"


def test_hyphenated_lastname():
    assert generate_paper_id("García-Luna", 2024, "Foo Bar") == "garcialuna2024foo"


def test_empty_lastname_fallback():
    """Falling back when lastname yields no alphanumeric characters."""
    result = generate_paper_id("---", 2024, "Title Here")
    assert result == "unknown2024title"


def test_empty_title_fallback():
    """When no meaningful word in title, use 'untitled' placeholder."""
    result = generate_paper_id("Smith", 2024, "A the of")
    assert result == "smith2024untitled"


def test_normalize_arxiv_strips_version():
    assert normalize_identifier("arxiv", "1706.03762v5") == ("1706.03762", "v5")
    assert normalize_identifier("arxiv", "1706.03762") == ("1706.03762", None)


def test_normalize_arxiv_leading_whitespace():
    assert normalize_identifier("arxiv", "  1706.03762v3  ") == ("1706.03762", "v3")


def test_normalize_doi_lowercases():
    assert normalize_identifier("doi", "10.1145/3442188.3445922")[0] == "10.1145/3442188.3445922"
    assert normalize_identifier("doi", "10.1145/XYZ")[0] == "10.1145/xyz"


def test_normalize_url_preserves_case():
    # URLs are case-sensitive in paths and querystrings; only compare as-is.
    assert normalize_identifier("url", "https://Example.com/Paper")[0] == "https://Example.com/Paper"


def test_find_existing_paper_by_doi(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/vaswani-2017-attention.md"
    write_frontmatter(str(paper), {
        "paper-id": "vaswani-2017-attention",
        "identifiers": {"doi": "10.xx/yy", "arxiv": "1706.03762"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.xx/yy"})
    assert found == "vaswani-2017-attention"


def test_find_existing_paper_by_arxiv_different_version(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/vaswani-2017-attention.md"
    write_frontmatter(str(paper), {
        "paper-id": "vaswani-2017-attention",
        "identifiers": {"arxiv": "1706.03762", "arxiv-version": "v3"},
    }, "")
    # Incoming is the same arxiv ID at a different version — should match (version stripped)
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"arxiv": "1706.03762v5"})
    assert found == "vaswani-2017-attention"


def test_find_existing_paper_by_arxiv_no_version_both_sides(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/x-2024-y.md"
    write_frontmatter(str(paper), {
        "paper-id": "x-2024-y",
        "identifiers": {"arxiv": "2401.12345"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"arxiv": "2401.12345"})
    assert found == "x-2024-y"


def test_find_existing_paper_doi_case_insensitive(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/x-2024-y.md"
    write_frontmatter(str(paper), {
        "paper-id": "x-2024-y",
        "identifiers": {"doi": "10.1145/AbCdEf"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.1145/abcdef"})
    assert found == "x-2024-y"


def test_find_existing_paper_no_match(tmp_wiki):
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.xx/zz"})
    assert found is None


def test_find_existing_paper_ignores_papers_without_identifiers(tmp_wiki):
    """A paper page with no identifiers frontmatter shouldn't crash lookup."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/orphan.md"
    write_frontmatter(str(paper), {"paper-id": "orphan"}, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.xx/yy"})
    assert found is None


def test_resolve_collision_appends_numeric_suffix(tmp_wiki):
    (tmp_wiki / "wiki/papers/smith-2020-neural.md").write_text("---\n---\n")
    result = resolve_collision(str(tmp_wiki), "smith-2020-neural")
    assert result == "smith-2020-neural-2"


def test_resolve_collision_finds_next_available(tmp_wiki):
    (tmp_wiki / "wiki/papers/smith-2020-neural.md").write_text("")
    (tmp_wiki / "wiki/papers/smith-2020-neural-2.md").write_text("")
    (tmp_wiki / "wiki/papers/smith-2020-neural-3.md").write_text("")
    result = resolve_collision(str(tmp_wiki), "smith-2020-neural")
    assert result == "smith-2020-neural-4"


def test_resolve_collision_no_collision(tmp_wiki):
    """If no collision, returns the proposed id unchanged."""
    result = resolve_collision(str(tmp_wiki), "brand-new-2025-paper")
    assert result == "brand-new-2025-paper"


def test_find_existing_paper_skips_malformed(tmp_wiki):
    """Malformed frontmatter in one paper should not break dedup lookup."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    # Write a malformed paper page
    bad = tmp_wiki / "wiki/papers/bad.md"
    bad.write_text("---\nkey: : malformed :\n  - indent error\n---\nBody.\n")
    # And a good one with the target identifier
    good = tmp_wiki / "wiki/papers/good.md"
    write_frontmatter(str(good), {
        "paper-id": "good",
        "identifiers": {"doi": "10.xx/yy"},
    }, "")
    # Lookup must still find the good one
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.xx/yy"})
    assert found == "good"


def test_ascii_fold_nordic_germanic_letters():
    """ø, æ, ß etc. should fold to ASCII equivalents."""
    assert generate_paper_id("Øster", 2024, "Foo Bar") == "oster2024foo"
    assert generate_paper_id("Müller", 2024, "Baz") == "muller2024baz"
    assert generate_paper_id("Straße", 2024, "Test") == "strasse2024test"
    assert generate_paper_id("Æther", 2024, "Qux") == "aether2024qux"
