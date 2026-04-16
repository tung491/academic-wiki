"""Wiki-root detection and listing."""
from __future__ import annotations

import os
from pathlib import Path


def find_active_wiki(start) -> str | None:
    """Walk up from `start` looking for a directory containing both CLAUDE.md AND wiki/.
    Returns the absolute path of that directory, or None if none is found.

    Accepts str or os.PathLike.
    """
    p = Path(os.fspath(start)).resolve()
    while True:
        if (p / "CLAUDE.md").exists() and (p / "wiki").is_dir():
            return str(p)
        if p.parent == p:
            return None
        p = p.parent


def list_wikis(base) -> list[str]:
    """List names of wiki-like subdirectories of `base`.
    A wiki-like subdir contains both CLAUDE.md and wiki/.
    Returns sorted list of names (not paths).

    Accepts str or os.PathLike.
    """
    basep = Path(os.fspath(base))
    if not basep.is_dir():
        return []
    out = []
    for child in basep.iterdir():
        if child.is_dir() and (child / "CLAUDE.md").exists() and (child / "wiki").is_dir():
            out.append(child.name)
    return sorted(out)
