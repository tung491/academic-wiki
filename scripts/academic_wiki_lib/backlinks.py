"""Atomic backlink insertion into wiki pages."""
from __future__ import annotations

import os
import re
from pathlib import Path

from academic_wiki_lib import entity_lock


_PATH_KIND_MAP = {
    "papers": "paper",
    "concepts": "concept",
    "methods": "method",
    "open-problems": "open-problem",
    "venues": "venue",
}


def _target_lock_kind_and_key(target_path: str) -> tuple[str, str]:
    """Map a wiki file path to (entity_lock kind, key).

    Examples:
        wiki/papers/<pid>.md        → ("paper", <pid>)
        wiki/concepts/<slug>.md     → ("concept", <slug>)
        wiki/methods/<slug>.md      → ("method", <slug>)
        wiki/open-problems/<slug>.md → ("open-problem", <slug>)
        wiki/venues/<slug>.md       → ("venue", <slug>)
    """
    p = Path(target_path)
    parts = p.parts
    if len(parts) < 3 or parts[0] != "wiki":
        raise ValueError(f"Not a wiki/ path: {target_path!r}")
    dir_name = parts[1]
    if dir_name not in _PATH_KIND_MAP:
        raise ValueError(f"Unknown wiki subdir: {dir_name!r} (in {target_path!r})")
    return _PATH_KIND_MAP[dir_name], p.stem


def insert_backlink(wiki_root, target_path: str, slug: str) -> bool:
    """Atomically insert [[<slug>]] into target_path where slug-words appear.

    Rule: only insert if slug has >=2 hyphen-separated tokens. No-op if
    [[<slug>]] already present or no eligible match.

    Returns True if a backlink was inserted, False otherwise.
    """
    if slug.count("-") == 0:
        return False  # single-word slugs are never auto-linked in v1

    kind, key = _target_lock_kind_and_key(target_path)
    abs_target = Path(os.fspath(wiki_root)) / target_path
    if not abs_target.exists():
        return False

    with entity_lock.acquire(wiki_root, kind=kind, key=key):
        content = abs_target.read_text()
        wikilink = f"[[{slug}]]"
        if wikilink in content:
            return False
        words_pattern = re.escape(slug.replace("-", " "))
        pattern = re.compile(r"\b" + words_pattern + r"\b", flags=re.IGNORECASE)
        m = pattern.search(content)
        if not m:
            return False
        new_content = content[:m.start()] + wikilink + content[m.end():]
        abs_target.write_text(new_content)
        return True
