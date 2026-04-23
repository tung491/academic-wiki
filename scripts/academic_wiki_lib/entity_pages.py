"""Atomic upsert for wiki entity pages (concept/method/open-problem)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from academic_wiki_lib import entity_lock
from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter

_VALID_KINDS = frozenset({"concept", "method", "open-problem"})
_DEFAULT_STATUS = {
    "concept": "active",
    "method": "active",
    "open-problem": "open",
}


def _page_path(wiki_root, kind: str, slug: str) -> Path:
    return Path(os.fspath(wiki_root)) / "wiki" / f"{kind}s" / f"{slug}.md"


def _render_new(slug: str, kind: str, title: str, paper_id: str,
                tags: list[str], body_contribution: str, status: str,
                today: str) -> tuple[dict[str, Any], str]:
    fm: dict[str, Any] = {
        "type": kind,
        "slug": slug,
        "status": status,
        "created": today,
        "updated": today,
        "aliases": [],
        "sources": [paper_id],
        "tags": list(tags),
    }
    body = f"# {title}\n\n## Definition\n\n{body_contribution}\n\n## Details\n\n## See Also\n\n## Counter-Arguments and Gaps\n"
    return fm, body


def _merge_existing(existing_fm: dict[str, Any], existing_body: str,
                    paper_id: str, tags: list[str],
                    body_contribution: str, today: str) -> tuple[dict[str, Any], str]:
    sources = list(existing_fm.get("sources") or [])
    if paper_id not in sources:
        sources.append(paper_id)
    existing_tags = list(existing_fm.get("tags") or [])
    for t in tags:
        if t not in existing_tags:
            existing_tags.append(t)
    existing_fm["sources"] = sources
    existing_fm["tags"] = existing_tags
    existing_fm["updated"] = today
    # Append attributed paragraph to body
    attribution = f"\n\nFrom [[{paper_id}]]: {body_contribution}\n"
    return existing_fm, existing_body.rstrip() + attribution


def upsert_entity(
    wiki_root,
    slug: str,
    kind: str,
    paper_id: str,
    title: str,
    tags: list[str],
    body_contribution: str,
    status_default: str | None = None,
) -> bool:
    """Atomically create or merge wiki/<kind>s/<slug>.md.

    On create: renders a minimal page from template with sources=[paper_id].
    On update: appends paper_id to sources (dedup), unions tags, bumps updated,
    appends body_contribution as an attributed paragraph.

    Returns True if the page was created, False if it existed and was merged.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown entity kind: {kind!r} (expected one of {sorted(_VALID_KINDS)})")

    status = status_default if status_default is not None else _DEFAULT_STATUS[kind]
    today = date.today().isoformat()
    path = _page_path(wiki_root, kind, slug)

    with entity_lock.acquire(wiki_root, kind=kind, key=slug):
        if path.exists():
            existing_fm, existing_body = read_frontmatter(path)
            fm, body = _merge_existing(existing_fm, existing_body, paper_id,
                                       tags, body_contribution, today)
            write_frontmatter(path, fm, body)
            return False
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            fm, body = _render_new(slug, kind, title, paper_id, tags,
                                   body_contribution, status, today)
            write_frontmatter(path, fm, body)
            return True
