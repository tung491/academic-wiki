"""Tests for lint-wiki.py deterministic checks per spec §5.5."""
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import write_frontmatter

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "lint-wiki.py")


def run_lint(wiki_root):
    """Run lint-wiki.py as a subprocess; return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["python3", SCRIPT, str(wiki_root)],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def _paper(tmp_wiki, slug, **fm_overrides):
    """Helper: write a minimal paper page with the given overrides."""
    body = fm_overrides.pop("_body", "Body.\n")
    fm = {
        "paper-id": slug, "type": "paper", "status": "read",
        "created": "2026-04-16", "updated": "2026-04-16",
        "title": "Title", "authors": [{"slug": "smith", "name": "Smith"}],
        "year": 2020, "venue": "x",
        "identifiers": {"doi": f"10.x/{slug}"},
        "aliases": [],
        "bib-file": f"raw/bib/{slug}.bib",
        "extract": f"raw/extracts/{slug}.md",
        "references-raw": [], "cites": [],
        "tags": ["field/nlp", "year/2020"],
    }
    fm.update(fm_overrides)
    write_frontmatter(str(tmp_wiki / "wiki/papers" / f"{slug}.md"), fm, body)
    # Also touch a bib file so missing-bibtex check doesn't fire unless told to
    (tmp_wiki / "raw/bib" / f"{slug}.bib").write_text(f"@misc{{{slug},}}\n")


def test_dead_link_is_flagged(tmp_wiki):
    _paper(tmp_wiki, "p1")
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/foo.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p1"],
            "tags": ["field/nlp"],
        },
        "See [[nonexistent]].\n\n## Counter-Arguments and Gaps\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "DEAD_LINK" in out
    assert "nonexistent" in out
    # Lint must NOT auto-create the stub
    assert not (tmp_wiki / "wiki/concepts/nonexistent.md").exists()


def test_alias_resolution_reports_but_does_not_flag_dead(tmp_wiki):
    """If a dead link matches an existing alias, flag as ALIAS_LINK, not DEAD_LINK."""
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/new-slug.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "aliases": ["old-slug"],
            "sources": ["p"],
            "tags": ["field/nlp"],
        },
        "Body.\n\n## Counter-Arguments and Gaps\n",
    )
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/referrer.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p"],
            "tags": ["field/nlp"],
        },
        "See [[old-slug]].\n\n## Counter-Arguments and Gaps\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "ALIAS_LINK" in out
    assert "old-slug" in out


def test_orphan_detected(tmp_wiki):
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/lonely.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p"],
            "tags": ["field/nlp"],
        },
        "No inbound links.\n\n## Counter-Arguments and Gaps\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "ORPHAN" in out


def test_missing_field_tag(tmp_wiki):
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/untagged.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p"],
            "tags": ["method/xyz"],  # no field/*
        },
        "Body.\n\n## Counter-Arguments and Gaps\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "MISSING_FIELD_TAG" in out


def test_stale_status_older_than_90_days(tmp_wiki):
    long_ago = (date.today() - timedelta(days=100)).isoformat()
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/old.md"),
        {
            "type": "concept", "status": "stale",
            "created": "2024-01-01", "updated": long_ago,
            "sources": ["p"],
            "tags": ["field/nlp"],
        },
        "Body.\n\n## Counter-Arguments and Gaps\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "STALE" in out


def test_stale_concept_180_days(tmp_wiki):
    """concept/method untouched >180 days should be flagged even without status: stale."""
    long_ago = (date.today() - timedelta(days=200)).isoformat()
    write_frontmatter(
        str(tmp_wiki / "wiki/methods/old.md"),
        {
            "type": "method", "status": "active",
            "created": "2024-01-01", "updated": long_ago,
            "sources": ["p"],
            "tags": ["field/nlp"],
        },
        "Body.\n\n## Counter-Arguments and Gaps\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "STALE" in out


def test_missing_counter_args_on_concept(tmp_wiki):
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/foo.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p"],
            "tags": ["field/nlp"],
        },
        "Body without the required section.\n",  # NO counter-args section
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "MISSING_SECTION" in out


def test_missing_counter_args_only_on_concept_and_method(tmp_wiki):
    """Other entity types (paper, open-problem, result, claim) do NOT require the section."""
    _paper(tmp_wiki, "p1")  # no counter-args; should NOT flag
    write_frontmatter(
        str(tmp_wiki / "wiki/open-problems/op.md"),
        {
            "type": "open-problem", "status": "open",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p1"],
            "tags": ["field/nlp"],
        },
        "No counter-args section needed here.\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "MISSING_SECTION" not in out


def test_invalid_cites_key(tmp_wiki):
    _paper(tmp_wiki, "p1", cites=["ghost-paper-id"])
    rc, out, _ = run_lint(tmp_wiki)
    assert "INVALID_CITES" in out
    assert "ghost-paper-id" in out


def test_missing_bibtex(tmp_wiki):
    _paper(tmp_wiki, "p1")
    # Remove the bib file created by helper
    (tmp_wiki / "raw/bib/p1.bib").unlink()
    rc, out, _ = run_lint(tmp_wiki)
    assert "MISSING_BIBTEX" in out


def test_bibtex_incomplete_flagged(tmp_wiki):
    _paper(tmp_wiki, "p1")
    # Overwrite the bib file with an incomplete marker
    (tmp_wiki / "raw/bib/p1.bib").write_text("% bib-incomplete: true\n@misc{p1,}\n")
    rc, out, _ = run_lint(tmp_wiki)
    assert "MISSING_BIBTEX" in out  # same issue class, since the bib is marked incomplete


def test_contradiction_listed(tmp_wiki):
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/x.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p1"],
            "tags": ["field/nlp"],
        },
        (
            "Body.\n\n"
            "> [!WARNING] Contradiction with [[y]]\n"
            "> They disagree on X.\n\n"
            "## Counter-Arguments and Gaps\n"
        ),
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "CONTRADICTION" in out or "WARNING" in out.upper()


def test_extract_integrity_paper_page_missing_extract(tmp_wiki):
    """Paper page exists but raw/extracts/<paper-id>.md is missing → warn."""
    _paper(tmp_wiki, "p1")
    # Do NOT create the extract file
    assert not (tmp_wiki / "raw/extracts/p1.md").exists()
    rc, out, _ = run_lint(tmp_wiki)
    assert "EXTRACT_MISSING" in out or "MISSING_EXTRACT" in out


def test_extract_integrity_extract_failed(tmp_wiki):
    """Extract has extract-status: failed → warn."""
    _paper(tmp_wiki, "p1")
    write_frontmatter(
        str(tmp_wiki / "raw/extracts/p1.md"),
        {
            "paper-id": "p1",
            "source-sha": "abc",
            "source-type": "pdf",
            "extractor": "x", "extractor-version": "1",
            "extracted-at": "2026-04-16T00:00:00Z",
            "ocr-used": True, "extract-status": "failed",
        },
        "empty\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "EXTRACT_FAILED" in out or "extract-status" in out.lower()


def test_index_drift(tmp_wiki):
    """Files in wiki/ that aren't in index.md should be flagged (and vice versa)."""
    _paper(tmp_wiki, "p1")
    # index.md mentions only "p2" which doesn't exist
    (tmp_wiki / "wiki/index.md").write_text(
        "# academic Wiki Index\n\n"
        "## field/nlp\n"
        "- [[p2]] — nonexistent entry (2026-04-16)\n"
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "INDEX_DRIFT" in out


def test_version_drift(tmp_wiki):
    """Paper page's arxiv-version is behind the latest in versions manifest."""
    _paper(
        tmp_wiki, "p1",
        identifiers={"arxiv": "1706.03762", "arxiv-version": "v3"},
    )
    # Versions manifest lists a newer v5
    (tmp_wiki / "raw/extracts/p1.versions.yml").write_text(
        "versions:\n"
        "  - version: v3\n"
        "    source-sha: abc\n"
        "    extracted-at: 2023-01-01T00:00:00Z\n"
        "  - version: v5\n"
        "    source-sha: def\n"
        "    extracted-at: 2026-04-16T00:00:00Z\n"
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "VERSION_DRIFT" in out


def test_ok_when_no_issues(tmp_wiki):
    """A clean wiki produces an OK status."""
    _paper(tmp_wiki, "p1")
    # Create the extract file so extract-missing doesn't fire
    write_frontmatter(
        str(tmp_wiki / "raw/extracts/p1.md"),
        {
            "paper-id": "p1",
            "source-sha": "abc",
            "source-type": "pdf",
            "extractor": "x", "extractor-version": "1",
            "extracted-at": "2026-04-16T00:00:00Z",
            "ocr-used": False, "extract-status": "complete",
        },
        "body\n",
    )
    # index.md references the paper
    (tmp_wiki / "wiki/index.md").write_text(
        "# academic Wiki Index\n\n"
        "## field/nlp\n"
        "- [[p1]] — title (2026-04-16)\n"
    )
    # The paper page needs a fake backlink to avoid being orphaned. Seed that:
    write_frontmatter(
        str(tmp_wiki / "wiki/concepts/foo.md"),
        {
            "type": "concept", "status": "active",
            "created": "2026-04-16", "updated": "2026-04-16",
            "sources": ["p1"],
            "tags": ["field/nlp"],
        },
        "See [[p1]].\n\n## Counter-Arguments and Gaps\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert rc == 0
    # Should not contain any of the issue markers (foo.md's backlink to p1 makes p1 non-orphan)
    # foo.md itself may still be orphan since nothing links to it
    # Accept either OK output OR a lint report with only ORPHAN for foo.md (expected)
    issue_tags = ["DEAD_LINK", "MISSING_FIELD_TAG", "MISSING_SECTION", "INVALID_CITES", "MISSING_BIBTEX", "INDEX_DRIFT", "VERSION_DRIFT", "EXTRACT_MISSING", "STALE"]
    for tag in issue_tags:
        assert tag not in out, f"Unexpected {tag} in clean wiki: {out}"


def test_lint_exit_code_is_zero_on_issues(tmp_wiki):
    """Lint reports findings but does NOT fail the exit code (callers can count issues)."""
    _paper(tmp_wiki, "p1")
    # Remove bib to create an issue
    (tmp_wiki / "raw/bib/p1.bib").unlink()
    rc, out, _ = run_lint(tmp_wiki)
    # Per spec §5.5, lint is reporting, not gating — exit code 0 even with issues
    assert rc == 0
    assert "MISSING_BIBTEX" in out
