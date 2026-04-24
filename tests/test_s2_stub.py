"""Unit tests for s2_stub.py."""
from __future__ import annotations

import pytest

from academic_wiki_lib.s2_stub import _compute_slug


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
