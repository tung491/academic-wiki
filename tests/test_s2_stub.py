"""Unit tests for s2_stub.py."""
from __future__ import annotations

import re

import pytest

from academic_wiki_lib.frontmatter import read_frontmatter
from academic_wiki_lib.s2_stub import _compute_slug


def _make_wiki_root(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki" / "papers").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("test\n")
    (wiki / "raw" / "papers").mkdir(parents=True)
    return wiki


def _sample_paper(**overrides):
    base = {
        "paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
        "title": "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer"],
        "year": 2017,
        "venue": "Advances in Neural Information Processing Systems",
        "abstract": "The dominant sequence transduction models...",
        "doi": "10.48550/arXiv.1706.03762",
        "arxiv": "1706.03762",
        "citationCount": 95234,
    }
    base.update(overrides)
    return base


class TestComputeSlug:
    def test_doi_present_returns_doi_slug(self):
        paper = {"doi": "10.1109/JIOT.2024.123456", "arxiv": "", "paperId": "abc"}
        assert _compute_slug(paper) == "s2-doi-10.1109_jiot.2024.123456"

    def test_doi_lowercased_and_special_chars_replaced(self):
        paper = {"doi": "10.1109/Has Space&Char", "arxiv": "", "paperId": ""}
        # `/` → `_`, lowercase, non-[a-z0-9._-] → `-`
        assert _compute_slug(paper) == "s2-doi-10.1109_has-space-char"

    def test_doi_truncated_at_100_chars(self):
        long_doi = "10.1234/" + "x" * 200
        paper = {"doi": long_doi, "arxiv": "", "paperId": ""}
        slug = _compute_slug(paper)
        # "s2-doi-" prefix is 7 chars; sanitized DOI body capped at 100
        assert len(slug) == 7 + 100
        assert slug.startswith("s2-doi-10.1234_")

    def test_arxiv_used_when_no_doi(self):
        paper = {"doi": "", "arxiv": "1706.03762", "paperId": "abc"}
        assert _compute_slug(paper) == "s2-arxiv-1706.03762"

    def test_arxiv_version_suffix_stripped(self):
        paper = {"doi": "", "arxiv": "1706.03762v5", "paperId": ""}
        assert _compute_slug(paper) == "s2-arxiv-1706.03762"

    def test_arxiv_prefix_stripped(self):
        paper = {"doi": "", "arxiv": "arxiv:1706.03762", "paperId": ""}
        assert _compute_slug(paper) == "s2-arxiv-1706.03762"

    def test_paperid_used_when_no_doi_or_arxiv(self):
        paper = {"doi": "", "arxiv": "", "paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776"}
        slug = _compute_slug(paper)
        assert slug.startswith("s2-pid-")
        # sha8 = first 8 hex chars of sha256(paperId)
        assert len(slug) == 7 + 8

    def test_paperid_produces_expected_sha8(self):
        import hashlib
        paper = {"doi": "", "arxiv": "", "paperId": "abc123"}
        expected_sha8 = hashlib.sha256(b"abc123").hexdigest()[:8]
        assert _compute_slug(paper) == f"s2-pid-{expected_sha8}"

    def test_no_identifier_returns_none(self):
        paper = {"doi": "", "arxiv": "", "paperId": ""}
        assert _compute_slug(paper) is None

    def test_missing_keys_treated_as_empty(self):
        paper = {}  # truly missing
        assert _compute_slug(paper) is None


class TestResolveDefaultWiki:
    def _make_wiki(self, base):
        """Helper: create a directory with CLAUDE.md + wiki/ markers."""
        base.mkdir(parents=True, exist_ok=True)
        (base / "CLAUDE.md").write_text("test\n")
        (base / "wiki").mkdir()
        return base

    def test_walks_up_from_cwd_to_find_active_wiki(self, tmp_path, monkeypatch):
        from academic_wiki_lib.s2_stub import resolve_default_wiki

        wiki = self._make_wiki(tmp_path / "vault" / "academic")
        deeper = wiki / "wiki" / "papers"
        deeper.mkdir(parents=True, exist_ok=True)
        monkeypatch.delenv("ACADEMIC_WIKI_DEFAULT", raising=False)

        assert resolve_default_wiki(str(deeper)) == str(wiki.resolve())

    def test_falls_back_to_env_var_when_cwd_no_match(self, tmp_path, monkeypatch):
        from academic_wiki_lib.s2_stub import resolve_default_wiki

        wiki = self._make_wiki(tmp_path / "vault" / "academic")
        non_wiki_cwd = tmp_path / "elsewhere"
        non_wiki_cwd.mkdir()
        monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

        assert resolve_default_wiki(str(non_wiki_cwd)) == str(wiki.resolve())

    def test_returns_none_when_neither_resolves(self, tmp_path, monkeypatch):
        from academic_wiki_lib.s2_stub import resolve_default_wiki

        non_wiki_cwd = tmp_path / "elsewhere"
        non_wiki_cwd.mkdir()
        monkeypatch.delenv("ACADEMIC_WIKI_DEFAULT", raising=False)

        assert resolve_default_wiki(str(non_wiki_cwd)) is None

    def test_invalid_env_var_path_returns_none(self, tmp_path, monkeypatch):
        from academic_wiki_lib.s2_stub import resolve_default_wiki

        non_wiki_cwd = tmp_path / "elsewhere"
        non_wiki_cwd.mkdir()
        monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(tmp_path / "does-not-exist"))

        assert resolve_default_wiki(str(non_wiki_cwd)) is None

    def test_env_var_path_without_wiki_markers_returns_none(self, tmp_path, monkeypatch):
        from academic_wiki_lib.s2_stub import resolve_default_wiki

        non_wiki_cwd = tmp_path / "elsewhere"
        non_wiki_cwd.mkdir()
        bare_dir = tmp_path / "bare"
        bare_dir.mkdir()
        monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(bare_dir))

        assert resolve_default_wiki(str(non_wiki_cwd)) is None

    def test_none_start_cwd_uses_env_var_only(self, tmp_path, monkeypatch):
        from academic_wiki_lib.s2_stub import resolve_default_wiki

        wiki = self._make_wiki(tmp_path / "vault" / "academic")
        monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

        assert resolve_default_wiki(None) == str(wiki.resolve())


class TestWriteS2Stubs:
    def test_writes_one_dir_per_paper(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        result = write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        slug = "s2-doi-10.48550_arxiv.1706.03762"
        stub = wiki / "raw" / "papers" / slug / f"{slug}.md"
        assert stub.is_file()
        assert result["written"] == 1
        assert result["skipped_existing"] == 0
        assert result["skipped_no_identifier"] == 0
        assert result["skipped_no_wiki"] is False
        assert result["failed"] == 0

    def test_frontmatter_has_expected_fields(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        slug = "s2-doi-10.48550_arxiv.1706.03762"
        stub = wiki / "raw" / "papers" / slug / f"{slug}.md"
        fm, body = read_frontmatter(stub)

        assert fm["title"] == "Attention Is All You Need"
        assert fm["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
        assert fm["year"] == 2017
        assert fm["venue"] == "Advances in Neural Information Processing Systems"
        assert fm["doi"] == "10.48550/arXiv.1706.03762"
        assert fm["arxiv"] == "1706.03762"
        assert fm["s2-paper-id"] == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
        assert fm["citation-count"] == 95234
        assert fm["source-url"] == "https://doi.org/10.48550/arXiv.1706.03762"
        assert fm["extractor"] == "s2-stub"
        assert fm["extract-status"] == "pending-s2"
        # ISO-8601 UTC: YYYY-MM-DDTHH:MM:SSZ
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", fm["extracted-at"])
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", fm["queried-at"])

        # Frontmatter MUST NOT contain paper-id (assigned by ingest later)
        assert "paper-id" not in fm

    def test_body_contains_abstract(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        slug = "s2-doi-10.48550_arxiv.1706.03762"
        _, body = read_frontmatter(wiki / "raw" / "papers" / slug / f"{slug}.md")
        assert "## Abstract" in body
        assert "The dominant sequence transduction models" in body

    def test_empty_abstract_writes_placeholder(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper(abstract="")], wiki_root=str(wiki))

        slug = "s2-doi-10.48550_arxiv.1706.03762"
        _, body = read_frontmatter(wiki / "raw" / "papers" / slug / f"{slug}.md")
        assert "## Abstract" in body
        assert "no abstract available" in body.lower()

    def test_source_url_falls_back_to_arxiv_when_no_doi(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper(doi="")], wiki_root=str(wiki))

        slug = "s2-arxiv-1706.03762"
        fm, _ = read_frontmatter(wiki / "raw" / "papers" / slug / f"{slug}.md")
        assert fm["source-url"] == "https://arxiv.org/abs/1706.03762"
        assert "doi" not in fm

    def test_source_url_falls_back_to_s2_when_no_doi_or_arxiv(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper(doi="", arxiv="")], wiki_root=str(wiki))

        # slug = s2-pid-<sha8>
        results = list((wiki / "raw" / "papers").iterdir())
        assert len(results) == 1
        fm, _ = read_frontmatter(results[0] / f"{results[0].name}.md")
        assert fm["source-url"] == (
            "https://www.semanticscholar.org/paper/"
            "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
        )

    def test_empty_optional_fields_are_omitted(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        # Year unknown, no venue
        write_s2_stubs(
            [_sample_paper(year=None, venue="")],
            wiki_root=str(wiki),
        )

        slug = "s2-doi-10.48550_arxiv.1706.03762"
        fm, _ = read_frontmatter(wiki / "raw" / "papers" / slug / f"{slug}.md")
        assert "year" not in fm
        assert "venue" not in fm

    def test_creates_raw_papers_if_missing(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = tmp_path / "academic"
        (wiki / "wiki").mkdir(parents=True)
        (wiki / "CLAUDE.md").write_text("test\n")
        # NOTE: raw/papers/ NOT pre-created

        result = write_s2_stubs([_sample_paper()], wiki_root=str(wiki))
        assert result["written"] == 1
        assert (wiki / "raw" / "papers").is_dir()


class TestWriteS2StubsEdgeCases:
    def test_idempotent_on_rerun(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))
        result2 = write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        assert result2["written"] == 0
        assert result2["skipped_existing"] == 1

    def test_no_wiki_root_returns_skipped(self):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        result = write_s2_stubs([_sample_paper()], wiki_root=None)

        assert result["skipped_no_wiki"] is True
        assert result["written"] == 0

    def test_empty_papers_list_is_noop(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        result = write_s2_stubs([], wiki_root=str(wiki))

        assert result == {
            "wiki_root": str(wiki),
            "written": 0,
            "skipped_existing": 0,
            "skipped_no_identifier": 0,
            "skipped_no_wiki": False,
            "failed": 0,
        }

    def test_paper_without_identifier_skipped(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        bad = {"title": "No IDs", "authors": ["A"], "year": 2024,
               "doi": "", "arxiv": "", "paperId": ""}
        result = write_s2_stubs([bad], wiki_root=str(wiki))

        assert result["skipped_no_identifier"] == 1
        assert result["written"] == 0
        assert list((wiki / "raw" / "papers").iterdir()) == []

    def test_mixed_batch_counts_are_correct(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        # Pre-write one stub so the second call hits skipped_existing
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        batch = [
            _sample_paper(),  # already exists
            _sample_paper(doi="10.1/new", arxiv=""),  # new
            {"doi": "", "arxiv": "", "paperId": ""},  # no identifier
        ]
        result = write_s2_stubs(batch, wiki_root=str(wiki))

        assert result["written"] == 1
        assert result["skipped_existing"] == 1
        assert result["skipped_no_identifier"] == 1
        assert result["failed"] == 0

    def test_atomic_write_no_tmp_file_on_success(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs, _compute_slug

        wiki = _make_wiki_root(tmp_path)
        paper = _sample_paper()
        write_s2_stubs([paper], wiki_root=str(wiki))

        slug = _compute_slug(paper)
        files = sorted(p.name for p in (wiki / "raw" / "papers" / slug).iterdir())
        assert files == [f"{slug}.md"]  # no .tmp leftover

    def test_per_paper_failure_isolated(self, tmp_path, monkeypatch):
        """If one paper write raises, the next paper still succeeds."""
        from academic_wiki_lib import s2_stub
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        original_write = s2_stub.write_frontmatter
        call_count = {"n": 0}

        def flaky(path, fm, body):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError("simulated disk full")
            return original_write(path, fm, body)

        monkeypatch.setattr(s2_stub, "write_frontmatter", flaky)

        batch = [
            _sample_paper(),  # will raise
            _sample_paper(doi="10.1/second", arxiv=""),  # will succeed
        ]
        result = write_s2_stubs(batch, wiki_root=str(wiki))

        assert result["failed"] == 1
        assert result["written"] == 1
        # The failed paper's partial directory should have been cleaned up
        failed_slug = "s2-doi-10.48550_arxiv.1706.03762"
        assert not (wiki / "raw" / "papers" / failed_slug).exists()

    def test_wiki_root_nonexistent_path_creates_papers_dir(self, tmp_path):
        """If wiki_root is a string that doesn't exist yet, write_s2_stubs trusts
        the input and creates raw/papers/ under it. The "treat nonexistent as
        no-wiki" rule lives in resolve_default_wiki, not here."""
        from academic_wiki_lib.s2_stub import write_s2_stubs

        ghost = tmp_path / "ghost"
        result = write_s2_stubs([_sample_paper()], wiki_root=str(ghost))

        assert result["written"] == 1
        assert (ghost / "raw" / "papers").is_dir()

    def test_partial_failure_cleanup_allows_retry(self, tmp_path, monkeypatch):
        """If write_frontmatter raises, the partial target_dir must be cleaned up
        so a future call can retry the same paper successfully (regression test
        for the bug fixed in commit e15393b)."""
        from academic_wiki_lib import s2_stub
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        slug = "s2-doi-10.48550_arxiv.1706.03762"
        target_dir = wiki / "raw" / "papers" / slug

        # First call: monkeypatch write_frontmatter to raise
        original_write = s2_stub.write_frontmatter

        def first_call_fails(path, fm, body):
            raise OSError("simulated failure")

        monkeypatch.setattr(s2_stub, "write_frontmatter", first_call_fails)
        result1 = write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        assert result1["failed"] == 1
        assert result1["written"] == 0
        # Cleanup must have removed the partial target_dir
        assert not target_dir.exists()

        # Second call: restore the real write_frontmatter; the same paper should succeed
        monkeypatch.setattr(s2_stub, "write_frontmatter", original_write)
        result2 = write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        assert result2["written"] == 1
        assert result2["skipped_existing"] == 0
        assert (target_dir / f"{slug}.md").is_file()
