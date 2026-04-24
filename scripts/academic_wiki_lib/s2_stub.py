"""Write S2 search results as clipper-compatible stubs into a wiki's raw/papers/."""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from academic_wiki_lib.frontmatter import write_frontmatter
from academic_wiki_lib.wiki_paths import find_active_wiki, _has_wiki_markers

_SLUG_PREFIX_DOI = "s2-doi-"
_SLUG_PREFIX_ARXIV = "s2-arxiv-"
_SLUG_PREFIX_PID = "s2-pid-"
_DOI_BODY_MAX = 100
_NON_SAFE_CHAR_RE = re.compile(r"[^a-z0-9._-]")
_ARXIV_VERSION_RE = re.compile(r"v\d+$")


def _sanitize_doi(doi: str) -> str:
    s = doi.lower().replace("/", "_")
    s = _NON_SAFE_CHAR_RE.sub("-", s)
    return s[:_DOI_BODY_MAX]


# arXiv IDs are short by nature: new-style "2312.12345" ≈ 10 chars, old-style "cs/0301013" similarly short.
def _normalize_arxiv(arxiv: str) -> str:
    s = arxiv.lower()
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


def _source_url(paper: dict) -> str | None:
    """Return the canonical source URL for the paper, or None if no identifier."""
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
    if paper.get("citationCount") is not None:  # 0 is a valid count
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


def _cleanup_partial(target_dir: Path) -> None:
    """Best-effort removal of a partially-created stub dir after a write failure."""
    try:
        if not target_dir.exists():
            return
        for p in target_dir.iterdir():
            try:
                p.unlink()
            except OSError:
                pass
        target_dir.rmdir()
    except OSError:
        pass


def write_s2_stubs(papers: list[dict], wiki_root: str | None) -> dict:
    """Write each paper as a clipper-style stub dir under <wiki_root>/raw/papers/.

    See spec §4.3 for the contract. Never raises; failures via the return dict.
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
            # Roll back partial state so a future retry can succeed
            # (otherwise the empty target_dir would short-circuit as skipped_existing).
            _cleanup_partial(target_dir)

    return summary
