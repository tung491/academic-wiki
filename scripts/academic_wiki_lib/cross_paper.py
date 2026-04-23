"""Cross-paper candidate detection helpers: top-K neighbors + report append."""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from academic_wiki_lib import entity_lock
from academic_wiki_lib.frontmatter import read_frontmatter


def _field_and_method_tags(tags: list[str]) -> set[str]:
    return {t for t in (tags or []) if t.startswith("field/") or t.startswith("method/")}


def _load_paper_meta(wiki_root, paper_id: str) -> tuple[set[str], int, str] | None:
    """Return (field_method_tags, year_int, paper_id) or None if missing."""
    path = Path(os.fspath(wiki_root)) / "wiki" / "papers" / f"{paper_id}.md"
    if not path.exists():
        return None
    fm, _ = read_frontmatter(path)
    tags = _field_and_method_tags(fm.get("tags") or [])
    year_raw = fm.get("year")
    try:
        year = int(year_raw)
    except (TypeError, ValueError):
        year = 0
    return (tags, year, paper_id)


def compute_top_k_neighbors(
    wiki_root,
    paper_id: str,
    pre_batch_paper_ids: list[str],
    k: int = 20,
) -> list[str]:
    """Rank pre-batch papers by shared field/* and method/* tags.

    Returns paper-ids sorted (shared desc, year desc, paper_id asc), filtered
    to positive overlap only, truncated to top k.
    """
    me = _load_paper_meta(wiki_root, paper_id)
    if me is None:
        return []
    my_tags = me[0]
    if not my_tags:
        return []

    scored: list[tuple[int, int, str]] = []
    for pid in pre_batch_paper_ids:
        other = _load_paper_meta(wiki_root, pid)
        if other is None:
            continue
        other_tags, other_year, other_pid = other
        shared = len(my_tags & other_tags)
        if shared == 0:
            continue
        scored.append((shared, other_year, other_pid))

    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [pid for _, _, pid in scored[:k]]


def _report_path(wiki_root) -> Path:
    today = date.today().isoformat()
    return Path(os.fspath(wiki_root)) / "outputs" / "reports" / f"{today}-promotion-candidates.md"


def _render_entry(entry: dict[str, str]) -> str:
    return (
        f"### Candidate: {entry['description']}\n"
        f"- **Type:** {entry['type']}\n"
        f"- **Paper A:** [[{entry['paper_a']}]] — \"{entry['quote_a']}\"\n"
        f"- **Paper B:** [[{entry['paper_b']}]] — \"{entry['quote_b']}\"\n"
        f"- **Relationship:** {entry['relationship']}\n"
        f"- **Action:** review — promote or leave as-is\n\n"
    )


_ENTRY_KEY_PATTERN = re.compile(
    r"- \*\*Type:\*\* (?P<type>\w+)\s*\n"
    r"- \*\*Paper A:\*\* \[\[(?P<a>[^\]]+)\]\].*?\n"
    r"- \*\*Paper B:\*\* \[\[(?P<b>[^\]]+)\]\]",
    flags=re.DOTALL,
)


def _existing_keys(content: str) -> set[tuple[str, str, str]]:
    """Extract (paper_a, paper_b, type) keys from existing report content."""
    keys: set[tuple[str, str, str]] = set()
    for m in _ENTRY_KEY_PATTERN.finditer(content):
        keys.add((m.group("a"), m.group("b"), m.group("type")))
    return keys


def append_candidates(wiki_root, entries: list[dict[str, str]]) -> None:
    """Atomically append candidate entries to today's promotion-candidates report.

    Dedupes by (paper_a, paper_b, type) against existing file contents before
    appending. Creates the file with a heading if it does not exist.
    """
    if not entries:
        return
    path = _report_path(wiki_root)
    with entity_lock.acquire(wiki_root, kind="reports", key="promotion-candidates"):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_text()
        else:
            existing = f"# Promotion Candidates — {date.today().isoformat()}\n\n"
        existing_keys = _existing_keys(existing)
        new_rendered = []
        for e in entries:
            key = (e["paper_a"], e["paper_b"], e["type"])
            if key in existing_keys:
                continue
            new_rendered.append(_render_entry(e))
            existing_keys.add(key)
        if new_rendered:
            path.write_text(existing + "".join(new_rendered))
        elif not path.exists():
            # Ensure file exists with header even if everything was deduped
            path.write_text(existing)
