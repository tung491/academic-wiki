# S2 Auto-Stub on Query — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each Semantic Scholar discovery call (`semantic_scholar_search`, `discover_related`, `get_paper_by_doi`) writes a clipper-compatible stub for every result into the active wiki's `raw/papers/<slug>/`, so the next `wiki ingest` batch-scan picks them up automatically.

**Architecture:** A new `scripts/academic_wiki_lib/s2_stub.py` module owns slug computation, wiki resolution, and stub writing. Both MCP servers' discovery tools (`academic_wiki_mcp/tools/discovery.py` and `semantic_scholar_mcp/tools/discovery.py`) gain a fire-and-forget hook around their return values. A 1-line edit to `skills/wiki/SKILL.md` step 5 of the clipper handler preserves `extractor: s2-stub` instead of overwriting it.

**Tech Stack:** Python 3.10+, pytest with `pytest-asyncio` (auto mode), `pyyaml` for frontmatter, `requests` mocked via `unittest.mock.patch`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-24-s2-auto-stub-design.md`

---

## File map

**Create:**
- `scripts/academic_wiki_lib/s2_stub.py` — new module: `_compute_slug`, `resolve_default_wiki`, `write_s2_stubs`
- `tests/test_s2_stub.py` — unit tests for the new module
- `tests/mcp/test_discovery_auto_stub.py` — integration tests for the integrated server's hook
- `tests/semantic_scholar_mcp/test_discovery_auto_stub.py` — integration tests for the standalone server's hook

**Modify:**
- `academic_wiki_mcp/tools/discovery.py` — register `get_paper_by_doi` as a new MCP tool; add hook to all 3 tools
- `semantic_scholar_mcp/tools/discovery.py` — add `sys.path` shim and hook to all 3 tools
- `skills/wiki/SKILL.md` — line 143: change `extractor: obsidian-clipper` line to a conditional rule

**No changes:**
- `s2_client.py` files (in either server)
- `identifier.py` files
- `pyproject.toml` (no new dependencies)
- Marketplace JSON

---

## Task 1: `s2_stub.py` slug computation

**Files:**
- Create: `scripts/academic_wiki_lib/s2_stub.py`
- Create: `tests/test_s2_stub.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_s2_stub.py`:

```python
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

    def test_paperid_deterministic(self):
        paper = {"doi": "", "arxiv": "", "paperId": "abc123"}
        assert _compute_slug(paper) == _compute_slug(paper)

    def test_no_identifier_returns_none(self):
        paper = {"doi": "", "arxiv": "", "paperId": ""}
        assert _compute_slug(paper) is None

    def test_missing_keys_treated_as_empty(self):
        paper = {}  # truly missing
        assert _compute_slug(paper) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py -v
```

Expected: `ModuleNotFoundError: No module named 'academic_wiki_lib.s2_stub'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/academic_wiki_lib/s2_stub.py`:

```python
"""Write S2 search results as clipper-compatible stubs into a wiki's raw/papers/."""
from __future__ import annotations

import hashlib
import re

_SLUG_PREFIX_DOI = "s2-doi-"
_SLUG_PREFIX_ARXIV = "s2-arxiv-"
_SLUG_PREFIX_PID = "s2-pid-"
_DOI_BODY_MAX = 100
_NON_SAFE_CHAR_RE = re.compile(r"[^a-z0-9._-]")
_ARXIV_VERSION_RE = re.compile(r"v\d+$")


def _sanitize_doi(doi: str) -> str:
    s = doi.strip().lower().replace("/", "_")
    s = _NON_SAFE_CHAR_RE.sub("-", s)
    return s[:_DOI_BODY_MAX]


def _normalize_arxiv(arxiv: str) -> str:
    s = arxiv.strip().lower()
    if s.startswith("arxiv:"):
        s = s[len("arxiv:"):]
    s = _ARXIV_VERSION_RE.sub("", s)
    return s


def _compute_slug(paper: dict) -> str | None:
    """Deterministic per-paper slug. Returns None if paper has no usable identifier.

    Priority: doi > arxiv > paperId. See spec §5.5.
    """
    doi = (paper.get("doi") or "").strip()
    if doi:
        return _SLUG_PREFIX_DOI + _sanitize_doi(doi)

    arxiv = (paper.get("arxiv") or "").strip()
    if arxiv:
        return _SLUG_PREFIX_ARXIV + _normalize_arxiv(arxiv)

    pid = (paper.get("paperId") or "").strip()
    if pid:
        sha8 = hashlib.sha256(pid.encode("utf-8")).hexdigest()[:8]
        return _SLUG_PREFIX_PID + sha8

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add scripts/academic_wiki_lib/s2_stub.py tests/test_s2_stub.py && \
  git commit -m "$(cat <<'EOF'
feat(s2-stub): add _compute_slug for deterministic per-paper slugs

DOI > arXiv > paperId priority per spec §5.5. Identifier-based slugs let
re-running the same S2 query map to the same on-disk path so the next
write call short-circuits via os.path.exists() in a later task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `resolve_default_wiki`

**Files:**
- Modify: `scripts/academic_wiki_lib/s2_stub.py`
- Modify: `tests/test_s2_stub.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s2_stub.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py::TestResolveDefaultWiki -v
```

Expected: 6 failures with `ImportError: cannot import name 'resolve_default_wiki'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/academic_wiki_lib/s2_stub.py`:

```python
import os
from pathlib import Path

from academic_wiki_lib.wiki_paths import find_active_wiki, _has_wiki_markers


def resolve_default_wiki(start_cwd: str | None = None) -> str | None:
    """Resolve the active wiki root.

    1. If start_cwd is provided, walk up via find_active_wiki(start_cwd). If found, return it.
    2. Read env var ACADEMIC_WIKI_DEFAULT. If set and the path has wiki markers, return it.
    3. Return None.
    """
    if start_cwd is not None:
        found = find_active_wiki(start_cwd)
        if found is not None:
            return found

    env_path = os.environ.get("ACADEMIC_WIKI_DEFAULT", "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_dir() and _has_wiki_markers(p):
            return str(p.resolve())

    return None
```

Note: `_has_wiki_markers` is private to `wiki_paths.py` but imported here intentionally — it's the canonical "is this a wiki?" check. If linting complains about the private import, we can wrap it in a small public helper later. For now, prefer the direct import to avoid duplicating the check.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py -v
```

Expected: 16 passed (10 from Task 1 + 6 new).

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add scripts/academic_wiki_lib/s2_stub.py tests/test_s2_stub.py && \
  git commit -m "$(cat <<'EOF'
feat(s2-stub): add resolve_default_wiki with cwd-walk + env-var fallback

Per spec §7: try find_active_wiki(start_cwd) first, then fall back to
ACADEMIC_WIKI_DEFAULT env var if the cwd isn't under a wiki. Returns
None if neither resolves so the caller can no-op safely.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `write_s2_stubs` happy path

**Files:**
- Modify: `scripts/academic_wiki_lib/s2_stub.py`
- Modify: `tests/test_s2_stub.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s2_stub.py`:

```python
import re

from academic_wiki_lib.frontmatter import read_frontmatter


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py::TestWriteS2Stubs -v
```

Expected: 8 failures with `ImportError: cannot import name 'write_s2_stubs'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/academic_wiki_lib/s2_stub.py`:

```python
from datetime import datetime, timezone

from academic_wiki_lib.frontmatter import write_frontmatter


def _source_url(paper: dict) -> str | None:
    doi = (paper.get("doi") or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    arxiv = (paper.get("arxiv") or "").strip()
    if arxiv:
        normalized = _normalize_arxiv(arxiv)
        return f"https://arxiv.org/abs/{normalized}"
    pid = (paper.get("paperId") or "").strip()
    if pid:
        return f"https://www.semanticscholar.org/paper/{pid}"
    return None


def _build_frontmatter(paper: dict, now_iso: str) -> dict:
    """Return the frontmatter dict for one stub. Empty/missing fields omitted."""
    fm: dict = {}
    if paper.get("title"):
        fm["title"] = paper["title"]
    if paper.get("authors"):
        fm["authors"] = list(paper["authors"])
    if paper.get("year"):
        fm["year"] = paper["year"]
    if (paper.get("venue") or "").strip():
        fm["venue"] = paper["venue"]
    if (paper.get("doi") or "").strip():
        fm["doi"] = paper["doi"]
    if (paper.get("arxiv") or "").strip():
        fm["arxiv"] = paper["arxiv"]
    if (paper.get("paperId") or "").strip():
        fm["s2-paper-id"] = paper["paperId"]
    if paper.get("citationCount") is not None:
        fm["citation-count"] = paper["citationCount"]
    src_url = _source_url(paper)
    if src_url:
        fm["source-url"] = src_url
    fm["extractor"] = "s2-stub"
    fm["extract-status"] = "pending-s2"
    fm["extracted-at"] = now_iso
    fm["queried-at"] = now_iso
    return fm


def _build_body(paper: dict) -> str:
    abstract = (paper.get("abstract") or "").strip()
    if not abstract:
        abstract = "*(no abstract available from Semantic Scholar)*"
    return f"## Abstract\n\n{abstract}\n"


def write_s2_stubs(papers: list[dict], wiki_root: str | None) -> dict:
    """Write each paper as a clipper-style stub dir under <wiki_root>/raw/papers/.

    See spec §4.3 for the contract.
    Never raises; failures reported via the return dict.
    """
    summary = {
        "wiki_root": wiki_root,
        "written": 0,
        "skipped_existing": 0,
        "skipped_no_identifier": 0,
        "skipped_no_wiki": False,
        "failed": 0,
    }

    if not wiki_root:
        summary["skipped_no_wiki"] = True
        return summary

    raw_papers = Path(wiki_root) / "raw" / "papers"
    raw_papers.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for paper in papers:
        slug = _compute_slug(paper)
        if slug is None:
            summary["skipped_no_identifier"] += 1
            continue

        target_dir = raw_papers / slug
        if target_dir.exists():
            summary["skipped_existing"] += 1
            continue

        try:
            target_dir.mkdir(parents=True, exist_ok=False)
            fm = _build_frontmatter(paper, now_iso)
            body = _build_body(paper)
            tmp = target_dir / f"{slug}.md.tmp"
            final = target_dir / f"{slug}.md"
            write_frontmatter(tmp, fm, body)
            os.rename(tmp, final)
            summary["written"] += 1
        except Exception:
            summary["failed"] += 1

    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py -v
```

Expected: 24 passed (16 prior + 8 new).

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add scripts/academic_wiki_lib/s2_stub.py tests/test_s2_stub.py && \
  git commit -m "$(cat <<'EOF'
feat(s2-stub): add write_s2_stubs happy path with atomic write

Builds clipper-compatible stub dirs under <wiki_root>/raw/papers/<slug>/
with frontmatter from S2 fields and abstract as body. Atomic write via
.md.tmp + os.rename so concurrent ingest never sees a partial file. Empty
optional fields are omitted from the YAML to keep frontmatter clean.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `write_s2_stubs` edge cases

**Files:**
- Modify: `tests/test_s2_stub.py`
- Modify: `scripts/academic_wiki_lib/s2_stub.py` (only if a test exposes a missing branch)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s2_stub.py`:

```python
import os as _os


class TestWriteS2StubsEdgeCases:
    def test_idempotent_on_rerun(self, tmp_path):
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))
        result2 = write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        assert result2["written"] == 0
        assert result2["skipped_existing"] == 1

    def test_no_wiki_root_returns_skipped(self, tmp_path):
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
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        slug = "s2-doi-10.48550_arxiv.1706.03762"
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

    def test_wiki_root_nonexistent_path_creates_papers_dir(self, tmp_path):
        """If wiki_root is a string that doesn't exist yet, mkdir(parents=True)
        in raw/papers creation handles it. Spec §4.5 says nonexistent path is
        treated as no-wiki — but that's the resolver's job; write_s2_stubs
        accepts whatever it's given. Verify the actual behavior.
        """
        from academic_wiki_lib.s2_stub import write_s2_stubs

        # Caller passes a path that doesn't exist. write_s2_stubs creates raw/papers/
        # under it and writes successfully. The "treat nonexistent as no-wiki" rule
        # lives in resolve_default_wiki, NOT in write_s2_stubs.
        ghost = tmp_path / "ghost"
        result = write_s2_stubs([_sample_paper()], wiki_root=str(ghost))

        assert result["written"] == 1
        assert (ghost / "raw" / "papers").is_dir()
```

The last test pins down a subtlety in the spec: §4.5 says "wiki_root doesn't exist on disk → treat as no-wiki." But the cleanest implementation puts that responsibility in `resolve_default_wiki` (which already requires `_has_wiki_markers`). `write_s2_stubs` itself trusts its input. The integration tests later verify the end-to-end path; this test documents the boundary.

If the spec intent is strictly "write_s2_stubs treats nonexistent as no-wiki" too, the spec should be updated. The test as written reflects the most defensible decomposition: `resolve_default_wiki` is the gatekeeper. (If reviewer disagrees, change the test to assert `skipped_no_wiki: True` and add a `Path(wiki_root).is_dir()` check at the top of `write_s2_stubs`.)

- [ ] **Step 2: Run tests to verify they fail or pass appropriately**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py::TestWriteS2StubsEdgeCases -v
```

Expected: most pass already because Task 3's implementation handles them; `test_per_paper_failure_isolated` and `test_atomic_write_no_tmp_file_on_success` should pass as-is. If any unexpectedly fail, fix the implementation.

- [ ] **Step 3: Fix any failing tests**

If any test fails, edit `s2_stub.py` to handle the missing case. Likely candidates: ensure the `try/except` catches `OSError` (it catches `Exception` already), ensure idempotence path is correct.

- [ ] **Step 4: Run all tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py -v
```

Expected: all green (Task 1+2+3 + 8 from Task 4 = 32 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add tests/test_s2_stub.py scripts/academic_wiki_lib/s2_stub.py && \
  git commit -m "$(cat <<'EOF'
test(s2-stub): cover idempotence, mixed batches, isolation on per-paper failure

Pins down spec §4.5 / §6.1 edge cases. Documents the decomposition
choice that resolve_default_wiki gates the "wiki exists?" check while
write_s2_stubs trusts its input.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire hook into `academic_wiki_mcp/tools/discovery.py`

**Files:**
- Modify: `academic_wiki_mcp/tools/discovery.py`
- Create: `tests/mcp/test_discovery_auto_stub.py`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/mcp/test_discovery_auto_stub.py`:

```python
"""Integration tests for the academic_wiki_mcp auto-stub hook."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from academic_wiki_mcp.tools.discovery import (
    semantic_scholar_search,
    discover_related,
    get_paper_by_doi,
)


def _mk_wiki(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("test\n")
    (wiki / "raw" / "papers").mkdir(parents=True)
    return wiki


def _s2_search_response():
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={"data": [
            {
                "paperId": "abc",
                "title": "Hooked Paper",
                "authors": [{"name": "A. Author"}],
                "year": 2024,
                "venue": "ICML",
                "abstract": "An abstract.",
                "externalIds": {"DOI": "10.1/hooked"},
                "citationCount": 5,
            },
        ]}),
    )


@pytest.mark.asyncio
async def test_search_writes_stub_when_wiki_resolved(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    with patch("requests.get", return_value=_s2_search_response()):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_hooked" / "s2-doi-10.1_hooked.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_search_returns_results_when_no_wiki(tmp_path, monkeypatch):
    """Hook is silent on no-wiki. Tool must return results normally."""
    monkeypatch.delenv("ACADEMIC_WIKI_DEFAULT", raising=False)
    monkeypatch.chdir(tmp_path)  # nowhere near a wiki

    with patch("requests.get", return_value=_s2_search_response()):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_returns_results_when_hook_raises(tmp_path, monkeypatch):
    """If write_s2_stubs raises, the tool still returns its S2 results."""
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    with patch("requests.get", return_value=_s2_search_response()), \
         patch("academic_wiki_lib.s2_stub.write_s2_stubs",
               side_effect=RuntimeError("bug in stub writer")):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_discover_related_writes_stubs_for_related_list(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    # discover_related fans out to references + citations + recommendations.
    # Mock all three by making requests.get return the same payload regardless.
    paper_block = {
        "paperId": "rel1",
        "title": "Related",
        "authors": [{"name": "B"}],
        "year": 2023,
        "venue": "NeurIPS",
        "abstract": "",
        "externalIds": {"DOI": "10.1/rel"},
        "citationCount": 0,
    }
    refs_resp = MagicMock(status_code=200, json=MagicMock(
        return_value={"data": [{"citedPaper": paper_block}]}))

    with patch("requests.get", return_value=refs_resp):
        result = await discover_related("10.1/source", limit=5)

    assert result["total_found"] >= 1
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_rel" / "s2-doi-10.1_rel.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_get_paper_by_doi_writes_stub(tmp_path, monkeypatch):
    """get_paper_by_doi is registered as a new MCP tool in this MCP server."""
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    single_resp = MagicMock(status_code=200, json=MagicMock(return_value={
        "paperId": "single",
        "title": "Single Lookup",
        "authors": [{"name": "C"}],
        "year": 2022,
        "venue": "AAAI",
        "abstract": "Brief.",
        "externalIds": {"DOI": "10.1/single"},
        "citationCount": 1,
    }))

    with patch("requests.get", return_value=single_resp):
        result = await get_paper_by_doi("10.1/single")

    assert result is not None
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_single" / "s2-doi-10.1_single.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_get_paper_by_doi_none_result_no_write(tmp_path, monkeypatch):
    """If the lookup returns None, no stub should be written."""
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    miss = MagicMock(status_code=404)
    with patch("requests.get", return_value=miss):
        result = await get_paper_by_doi("10.1/missing")

    assert result is None
    assert list((wiki / "raw" / "papers").iterdir()) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/mcp/test_discovery_auto_stub.py -v
```

Expected: `ImportError: cannot import name 'get_paper_by_doi' from 'academic_wiki_mcp.tools.discovery'` plus other failures because the hook isn't wired.

- [ ] **Step 3: Modify `academic_wiki_mcp/tools/discovery.py`**

Replace the file's contents with the following. The diff: add `os` and stub-import, register `get_paper_by_doi` as a new MCP tool, and wrap each tool's return value in the hook.

```python
from __future__ import annotations

import os

from academic_wiki_mcp import mcp
from academic_wiki_mcp.identifier import detect
from academic_wiki_mcp.s2_client import (
    S2_FIELDS,
    S2_GRAPH,
    _normalize_s2_paper,
    _s2_get,
    get_paper_by_doi as _get_paper_by_doi,
)

S2_RECS = "https://api.semanticscholar.org/recommendations/v1"


def _stub_papers(papers: list[dict]) -> None:
    """Best-effort: write S2 results to the active wiki's raw/papers/.
    Never raises — hook failures must not break the tool call."""
    try:
        from academic_wiki_lib.s2_stub import write_s2_stubs, resolve_default_wiki
        write_s2_stubs(papers, wiki_root=resolve_default_wiki(os.getcwd()))
    except Exception:
        pass


async def _search(query: str, venue: str | None = None, year: str | None = None, limit: int = 10) -> list[dict]:
    params: dict[str, str] = {"query": query, "limit": str(limit), "fields": S2_FIELDS}
    if venue:
        params["venue"] = venue
    if year:
        params["year"] = year
    resp = _s2_get(f"{S2_GRAPH}/paper/search", params=params)
    if not resp or resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("data") or [])]


async def _references(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/references",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citedPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citedPaper")
    ]


async def _citations(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/citations",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citingPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citingPaper")
    ]


async def _recommendations(paper_id: str, limit: int = 20) -> list[dict]:
    resp = _s2_get(
        f"{S2_RECS}/papers/forpaper/{paper_id}",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code == 404:
        return []
    if resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("recommendedPapers") or [])]


def _resolve_s2_id(identifier: str) -> str:
    id_type, raw = detect(identifier)
    if id_type == "doi":
        return f"DOI:{raw}"
    if id_type == "arxiv":
        return f"ARXIV:{raw}"
    return identifier


@mcp.tool()
async def semantic_scholar_search(
    query: str,
    venue: str | None = None,
    year: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Semantic Scholar for papers by keyword query."""
    results = await _search(query, venue=venue, year=year, limit=limit)
    _stub_papers(results)
    return results


@mcp.tool()
async def get_paper_by_doi(doi: str) -> dict | None:
    """Fetch a single paper from Semantic Scholar by DOI. Returns None if not found."""
    result = _get_paper_by_doi(doi)
    if result is not None:
        _stub_papers([result])
    return result


@mcp.tool()
async def discover_related(identifier: str, limit: int = 10) -> dict:
    """Discover related papers via Semantic Scholar citation graph and recommendations."""
    s2_id = _resolve_s2_id(identifier)

    refs = await _references(s2_id, limit=50)
    cites = await _citations(s2_id, limit=50)
    recs = await _recommendations(s2_id, limit=20)

    seen: set[str] = set()
    combined: list[dict] = []
    for paper in refs + cites + recs:
        pid = paper["paperId"]
        if pid and pid not in seen:
            seen.add(pid)
            combined.append(paper)

    combined.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    related = combined[:limit]
    _stub_papers(related)
    return {"related": related, "total_found": len(combined)}
```

- [ ] **Step 4: Run all relevant tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/mcp/test_discovery_auto_stub.py tests/mcp/test_discovery.py -v
```

Expected: 6 new auto-stub tests pass; existing `test_discovery.py` tests still pass (the unwrapped `_search`/`_references` helpers are unchanged).

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add academic_wiki_mcp/tools/discovery.py tests/mcp/test_discovery_auto_stub.py && \
  git commit -m "$(cat <<'EOF'
feat(academic-wiki-mcp): auto-write S2 stubs to wiki/raw/papers/ on each query

semantic_scholar_search, discover_related, and get_paper_by_doi (newly
registered as an MCP tool here) now write a clipper-compatible stub for
every result into the active wiki's raw/papers/. Hook is fire-and-forget;
exceptions are swallowed so a wiki-write failure never breaks the tool.

Spec: docs/superpowers/specs/2026-04-24-s2-auto-stub-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Wire hook into `semantic_scholar_mcp/tools/discovery.py`

**Files:**
- Modify: `semantic_scholar_mcp/tools/discovery.py`
- Create: `tests/semantic_scholar_mcp/test_discovery_auto_stub.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/semantic_scholar_mcp/test_discovery_auto_stub.py`. The body is identical to `tests/mcp/test_discovery_auto_stub.py` from Task 5 but imports from `semantic_scholar_mcp.tools.discovery`:

```python
"""Integration tests for the semantic_scholar_mcp standalone auto-stub hook."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from semantic_scholar_mcp.tools.discovery import (
    semantic_scholar_search,
    discover_related,
    get_paper_by_doi,
)


def _mk_wiki(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("test\n")
    (wiki / "raw" / "papers").mkdir(parents=True)
    return wiki


def _s2_search_response():
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={"data": [
            {
                "paperId": "abc",
                "title": "Hooked Paper",
                "authors": [{"name": "A. Author"}],
                "year": 2024,
                "venue": "ICML",
                "abstract": "An abstract.",
                "externalIds": {"DOI": "10.1/standalone"},
                "citationCount": 5,
            },
        ]}),
    )


@pytest.mark.asyncio
async def test_search_writes_stub_when_wiki_resolved(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    with patch("requests.get", return_value=_s2_search_response()):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_standalone" / "s2-doi-10.1_standalone.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_search_returns_results_when_no_wiki(tmp_path, monkeypatch):
    monkeypatch.delenv("ACADEMIC_WIKI_DEFAULT", raising=False)
    monkeypatch.chdir(tmp_path)

    with patch("requests.get", return_value=_s2_search_response()):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_returns_results_when_hook_raises(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    with patch("requests.get", return_value=_s2_search_response()), \
         patch("academic_wiki_lib.s2_stub.write_s2_stubs",
               side_effect=RuntimeError("bug in stub writer")):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_discover_related_writes_stubs(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    paper_block = {
        "paperId": "rel1",
        "title": "Related",
        "authors": [{"name": "B"}],
        "year": 2023,
        "venue": "NeurIPS",
        "abstract": "",
        "externalIds": {"DOI": "10.1/standalone-rel"},
        "citationCount": 0,
    }
    refs_resp = MagicMock(status_code=200, json=MagicMock(
        return_value={"data": [{"citedPaper": paper_block}]}))

    with patch("requests.get", return_value=refs_resp):
        result = await discover_related("10.1/source", limit=5)

    assert result["total_found"] >= 1
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_standalone-rel" / "s2-doi-10.1_standalone-rel.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_get_paper_by_doi_writes_stub(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    single_resp = MagicMock(status_code=200, json=MagicMock(return_value={
        "paperId": "single",
        "title": "Single Lookup",
        "authors": [{"name": "C"}],
        "year": 2022,
        "venue": "AAAI",
        "abstract": "Brief.",
        "externalIds": {"DOI": "10.1/standalone-single"},
        "citationCount": 1,
    }))

    with patch("requests.get", return_value=single_resp):
        result = await get_paper_by_doi("10.1/standalone-single")

    assert result is not None
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_standalone-single" / "s2-doi-10.1_standalone-single.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_get_paper_by_doi_none_result_no_write(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    miss = MagicMock(status_code=404)
    with patch("requests.get", return_value=miss):
        result = await get_paper_by_doi("10.1/missing")

    assert result is None
    assert list((wiki / "raw" / "papers").iterdir()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/semantic_scholar_mcp/test_discovery_auto_stub.py -v
```

Expected: 6 failures because the hook isn't wired into the standalone server's discovery.py.

- [ ] **Step 3: Modify `semantic_scholar_mcp/tools/discovery.py`**

The standalone server is already separate, so it doesn't have `academic_wiki_lib` on its path. Add a `sys.path` shim at the top, then add the same `_stub_papers` helper and wrap each tool's return.

Replace the file with:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make academic_wiki_lib importable when this MCP runs from the parent repo.
# When the standalone is later extracted, this path won't resolve and the
# import inside _stub_papers will fail silently (caught by the try/except).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from semantic_scholar_mcp import mcp
from semantic_scholar_mcp.identifier import detect
from semantic_scholar_mcp.s2_client import (
    S2_FIELDS,
    S2_GRAPH,
    _normalize_s2_paper,
    _s2_get,
    get_paper_by_doi as _get_paper_by_doi,
)

S2_RECS = "https://api.semanticscholar.org/recommendations/v1"


def _stub_papers(papers: list[dict]) -> None:
    """Best-effort: write S2 results to the active wiki's raw/papers/."""
    try:
        from academic_wiki_lib.s2_stub import write_s2_stubs, resolve_default_wiki
        write_s2_stubs(papers, wiki_root=resolve_default_wiki(os.getcwd()))
    except Exception:
        pass


async def _search(query: str, venue: str | None = None, year: str | None = None, limit: int = 10) -> list[dict]:
    params: dict[str, str] = {"query": query, "limit": str(limit), "fields": S2_FIELDS}
    if venue:
        params["venue"] = venue
    if year:
        params["year"] = year
    resp = _s2_get(f"{S2_GRAPH}/paper/search", params=params)
    if not resp or resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("data") or [])]


async def _references(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/references",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citedPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citedPaper")
    ]


async def _citations(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/citations",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citingPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citingPaper")
    ]


async def _recommendations(paper_id: str, limit: int = 20) -> list[dict]:
    resp = _s2_get(
        f"{S2_RECS}/papers/forpaper/{paper_id}",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code == 404:
        return []
    if resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("recommendedPapers") or [])]


def _resolve_s2_id(identifier: str) -> str:
    id_type, raw = detect(identifier)
    if id_type == "doi":
        return f"DOI:{raw}"
    if id_type == "arxiv":
        return f"ARXIV:{raw}"
    return identifier


@mcp.tool()
async def semantic_scholar_search(
    query: str,
    venue: str | None = None,
    year: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Semantic Scholar for papers by keyword query.

    year accepts single years ("2020") or ranges ("2020-2023", "2020-").
    """
    results = await _search(query, venue=venue, year=year, limit=limit)
    _stub_papers(results)
    return results


@mcp.tool()
async def get_paper_by_doi(doi: str) -> dict | None:
    """Fetch a single paper from Semantic Scholar by DOI. Returns None if not found."""
    result = _get_paper_by_doi(doi)
    if result is not None:
        _stub_papers([result])
    return result


@mcp.tool()
async def discover_related(identifier: str, limit: int = 10) -> dict:
    """Discover related papers via Semantic Scholar citation graph and recommendations.

    identifier: DOI, arXiv ID (with or without prefix), or S2 paper ID.
    """
    s2_id = _resolve_s2_id(identifier)

    refs = await _references(s2_id, limit=50)
    cites = await _citations(s2_id, limit=50)
    recs = await _recommendations(s2_id, limit=20)

    seen: set[str] = set()
    combined: list[dict] = []
    for paper in refs + cites + recs:
        pid = paper["paperId"]
        if pid and pid not in seen:
            seen.add(pid)
            combined.append(paper)

    combined.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    related = combined[:limit]
    _stub_papers(related)
    return {"related": related, "total_found": len(combined)}
```

- [ ] **Step 4: Run all relevant tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/semantic_scholar_mcp/ tests/mcp/test_discovery_auto_stub.py -v
```

Expected: all green. The standalone server's existing `tests/semantic_scholar_mcp/test_discovery.py` should still pass (helpers unchanged).

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add semantic_scholar_mcp/tools/discovery.py tests/semantic_scholar_mcp/test_discovery_auto_stub.py && \
  git commit -m "$(cat <<'EOF'
feat(s2-mcp): auto-write S2 stubs to wiki/raw/papers/ on each query

Standalone server now mirrors the integrated MCP behavior: each
semantic_scholar_search, discover_related, and get_paper_by_doi call
writes a stub per result into the active wiki via academic_wiki_lib.s2_stub.
sys.path shim at module top makes academic_wiki_lib importable from this
sibling repo location; when the package is later extracted to its own
repo the import will fail silently and the hook becomes a no-op.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update `skills/wiki/SKILL.md` to preserve `extractor: s2-stub`

**Files:**
- Modify: `skills/wiki/SKILL.md` (line 143 area, in the Clipper directory ingest block)

This task is a documentation-only change. There is no Python test for it because the clipper handler is executed by the LLM running the `wiki ingest` skill, not by Python code. The end-to-end behavior is verified manually after Task 8 lands and the user runs an actual `wiki ingest` against an S2 stub.

- [ ] **Step 1: Read the current step 5 to confirm the line content**

```bash
cd /home/tung491/Work/academic_wiki && sed -n '136,145p' skills/wiki/SKILL.md
```

Expected output (line 143 is `   - extractor: obsidian-clipper`).

- [ ] **Step 2: Modify SKILL.md**

Use the `Edit` tool to replace the unconditional bullet with a conditional rule. The exact change:

Replace:
```
   - `extractor: obsidian-clipper`
```

With:
```
   - `extractor` — set to `obsidian-clipper` UNLESS the existing frontmatter already has `extractor: s2-stub` (in which case preserve `s2-stub` so future audits can identify entries that were first cached by an S2 query rather than clipped by the user).
```

- [ ] **Step 3: Verify the diff**

```bash
cd /home/tung491/Work/academic_wiki && git diff skills/wiki/SKILL.md
```

Expected: a single-line replacement at line 143 with the conditional rule above.

- [ ] **Step 4: Run all wiki tests as a sanity check** (no behavior change is expected — this only affects skill execution, not Python code)

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/ -v --ignore=tests/mcp -x
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add skills/wiki/SKILL.md && \
  git commit -m "$(cat <<'EOF'
docs(wiki-skill): preserve extractor: s2-stub during clipper ingest merge

Step 5 of the Clipper directory ingest block previously overwrote the
extractor field with obsidian-clipper unconditionally. The S2 auto-stub
feature seeds clipper-style dirs with extractor: s2-stub; preserving that
value lets future lint/audit code distinguish S2-only metadata stubs from
real clipped extractions.

Spec: docs/superpowers/specs/2026-04-24-s2-auto-stub-design.md §5.4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: End-to-end test — stub becomes a clipper-compatible source

**Files:**
- Modify: `tests/test_s2_stub.py`

The full ingest flow lives in `skills/wiki/SKILL.md` and runs in the LLM, so we cannot literally execute `wiki ingest` from pytest. Instead, this test verifies the structural contract: a stub written by `write_s2_stubs` is readable by the underlying Python primitives that the skill orchestrates (`read_frontmatter`, `generate_paper_id`, `find_existing_paper_by_identifiers`). If those primitives accept the stub, the skill's pipeline will too.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_s2_stub.py`:

```python
class TestStubIsClipperCompatible:
    """Verify the stub is consumable by the Python helpers the wiki ingest
    skill orchestrates. We can't run the full skill from pytest, but we can
    verify the contract at the module boundary."""

    def test_stub_frontmatter_round_trips(self, tmp_path):
        from academic_wiki_lib.frontmatter import read_frontmatter
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))
        slug = "s2-doi-10.48550_arxiv.1706.03762"
        stub_md = wiki / "raw" / "papers" / slug / f"{slug}.md"

        fm, body = read_frontmatter(stub_md)
        assert fm["title"] == "Attention Is All You Need"
        assert "## Abstract" in body

    def test_stub_metadata_yields_expected_paper_id(self, tmp_path):
        """generate_paper_id is what the skill calls during ingest pipeline
        step 5. Verify the stub's metadata produces a sensible paper-id."""
        from academic_wiki_lib.frontmatter import read_frontmatter
        from academic_wiki_lib.paper_id import generate_paper_id
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))
        slug = "s2-doi-10.48550_arxiv.1706.03762"
        fm, _ = read_frontmatter(wiki / "raw" / "papers" / slug / f"{slug}.md")

        # First-author last name, year, first meaningful word of title
        last_name = fm["authors"][0].split()[-1]  # "Vaswani"
        pid = generate_paper_id(last_name, fm["year"], fm["title"])
        assert pid == "vaswani2017attention"

    def test_stub_dedup_matches_existing_paper_via_identifiers(self, tmp_path):
        """Verify pass 2 dedup (by DOI) sees the stub via find_existing_paper_by_identifiers
        once the stub has been ingested with a paper-id. We simulate the post-ingest state by
        writing a wiki/papers/<paper-id>.md with the same DOI in identifiers, then running the
        lookup with the stub's DOI."""
        from academic_wiki_lib.paper_id import find_existing_paper_by_identifiers
        from academic_wiki_lib.frontmatter import write_frontmatter
        from academic_wiki_lib.s2_stub import write_s2_stubs

        wiki = _make_wiki_root(tmp_path)
        # Write a wiki paper with the SAME DOI that the upcoming S2 stub will carry
        write_frontmatter(
            wiki / "wiki" / "papers" / "vaswani2017attention.md",
            {
                "paper-id": "vaswani2017attention",
                "identifiers": {"doi": "10.48550/arXiv.1706.03762"},
            },
            "# Attention Is All You Need\n",
        )
        # Now write the S2 stub
        write_s2_stubs([_sample_paper()], wiki_root=str(wiki))

        # The skill's pass 2 dedup would call this lookup and find the existing paper
        existing = find_existing_paper_by_identifiers(
            str(wiki), {"doi": "10.48550/arXiv.1706.03762"})
        assert existing == "vaswani2017attention"
```

- [ ] **Step 2: Run the new tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_s2_stub.py::TestStubIsClipperCompatible -v
```

Expected: 3 passed (these test interactions with existing helpers; no new code needed).

- [ ] **Step 3: Run the full test suite**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/ -v
```

Expected: all green. New tests added: ~32 in `test_s2_stub.py` + 6 in `test_discovery_auto_stub.py` (academic_wiki_mcp) + 6 in `test_discovery_auto_stub.py` (semantic_scholar_mcp).

- [ ] **Step 4: Commit**

```bash
cd /home/tung491/Work/academic_wiki && \
  git add tests/test_s2_stub.py && \
  git commit -m "$(cat <<'EOF'
test(s2-stub): verify stubs are clipper-compatible at module boundaries

Three end-to-end tests that pin the contract between S2 stubs and the
helpers the wiki ingest skill orchestrates: read_frontmatter round-trips
the YAML, generate_paper_id produces the expected key, and pass-2 dedup
via find_existing_paper_by_identifiers correctly locates an existing
paper with the same DOI. The full ingest flow lives in SKILL.md (LLM-
executed), so this is the strongest reproducible coverage we can give it
from pytest.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Verification checklist

After all 8 tasks land:

- [ ] `python -m pytest tests/ -v` passes everything (~470+ existing tests + ~44 new).
- [ ] `git log --oneline | head -10` shows 8 new commits with the spec-prescribed messages.
- [ ] Manual smoke test (optional, requires a real wiki):
  ```bash
  export ACADEMIC_WIKI_DEFAULT="$HOME/Documents/Obsidian Vault/03-Resources/academic"
  # Trigger one of the S2 tools through Claude Code or via the MCP server directly
  # Then:
  ls "$ACADEMIC_WIKI_DEFAULT/raw/papers/s2-"*
  # Inspect one stub:
  cat "$ACADEMIC_WIKI_DEFAULT/raw/papers/s2-doi-..."/s2-doi-...md
  # Run wiki ingest to promote it
  /academic-wiki:wiki ingest
  # Verify the resulting wiki/papers/<paper-id>.md has extractor: s2-stub preserved
  ```

## Out of scope (deferred per spec §11)

- O-1: marking dedup'd S2 stubs with `extract-status: duplicate` to skip on future batch scans
- O-2: refreshing `queried-at` on re-query without rewriting frontmatter
- O-4: standalone fallback when `semantic_scholar_mcp` is extracted to its own repo
