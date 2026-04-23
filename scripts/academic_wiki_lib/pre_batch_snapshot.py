"""Pre-batch snapshot: the list of wiki files that existed at batch start.

Stored separately from the checkpoint (checkpoint stays small; snapshot can be
60KB+). Subagents read this file to scope their backlink audit step.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

SNAPSHOT_FILENAME = ".pre-batch-snapshot.yml"
_SCAN_SUBDIRS = ("papers", "concepts", "methods", "open-problems", "venues")


def snapshot_path(wiki_root) -> Path:
    return Path(os.fspath(wiki_root)) / "outputs" / SNAPSHOT_FILENAME


def scan_targets(wiki_root) -> list[str]:
    """Walk wiki/{papers,concepts,methods,open-problems,venues}/ and return
    a sorted list of relative paths (e.g., 'wiki/papers/foo.md').

    Scope is intentionally limited to the five directories that backlinks.py
    can lock. wiki/claims/ and wiki/results/ exist (cross-paper promotion
    targets) but are not auto-linked during compile.
    """
    root = Path(os.fspath(wiki_root))
    results: list[str] = []
    for sub in _SCAN_SUBDIRS:
        sub_dir = root / "wiki" / sub
        if not sub_dir.is_dir():
            continue
        for p in sorted(sub_dir.glob("*.md")):
            results.append(f"wiki/{sub}/{p.name}")
    return results


def write_snapshot(wiki_root, targets: list[str]) -> None:
    """Write the snapshot file with targets list."""
    path = snapshot_path(wiki_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"targets": list(targets)}, f, sort_keys=False,
                  allow_unicode=True, default_flow_style=False)


def read_snapshot(wiki_root) -> list[str]:
    """Read the snapshot's targets list. Returns [] if file missing."""
    path = snapshot_path(wiki_root)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    return list(data.get("targets") or [])


def delete_snapshot(wiki_root) -> None:
    """Delete the snapshot file if present."""
    path = snapshot_path(wiki_root)
    if path.exists():
        path.unlink()
