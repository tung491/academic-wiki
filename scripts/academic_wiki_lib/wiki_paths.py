"""Wiki-root detection and listing."""
from __future__ import annotations

import os
from pathlib import Path


def _has_wiki_markers(p: Path) -> bool:
    """True iff `p/CLAUDE.md` is a file AND `p/wiki/` is a directory."""
    return (p / "CLAUDE.md").is_file() and (p / "wiki").is_dir()


def find_active_wiki(start) -> str | None:
    """Walk up from `start` looking for a directory with wiki markers.
    Returns the absolute path of that directory, or None if none is found.

    Accepts str or os.PathLike.
    """
    p = Path(os.fspath(start)).resolve()
    while True:
        if _has_wiki_markers(p):
            return str(p)
        if p.parent == p:
            return None
        p = p.parent


def list_wikis(base) -> list[str]:
    """List names (not paths) of wiki-like subdirectories of `base`.
    A wiki-like subdir has a `CLAUDE.md` file AND a `wiki/` directory.
    Returns sorted list. Returns [] on missing or unreadable `base`.

    Accepts str or os.PathLike.
    """
    basep = Path(os.fspath(base))
    if not basep.is_dir():
        return []
    try:
        children = list(basep.iterdir())
    except (PermissionError, OSError):
        return []
    out = []
    for child in children:
        try:
            if child.is_dir() and _has_wiki_markers(child):
                out.append(child.name)
        except (PermissionError, OSError):
            continue
    return sorted(out)
