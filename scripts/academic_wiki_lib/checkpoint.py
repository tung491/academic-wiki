"""Compile checkpoint management for batch mode."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import yaml

CHECKPOINT_FILENAME = ".compile-checkpoint.yml"
STALE_THRESHOLD = timedelta(hours=24)


def _checkpoint_path(wiki_root) -> Path:
    return Path(os.fspath(wiki_root)) / "outputs" / CHECKPOINT_FILENAME


def create_checkpoint(
    wiki_root,
    papers: list[tuple[str, str]],
    wave_size: int,
    squash_base: str = "",
) -> dict[str, Any]:
    """Create a new checkpoint file. Returns the checkpoint dict."""
    cp: dict[str, Any] = {
        "run-id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "in-progress",
        "total": len(papers),
        "wave-size": wave_size,
        "last-completed-wave": -1,
        "papers": {pid: "pending" for pid, _ in papers},
        "errors": {},
        "squash-base": squash_base,
        "wave-commits": [],
    }
    write_checkpoint(wiki_root, cp)
    return cp


def read_checkpoint(wiki_root) -> dict[str, Any] | None:
    """Read checkpoint from disk. Returns None if no checkpoint exists."""
    path = _checkpoint_path(wiki_root)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_checkpoint(wiki_root, cp: dict[str, Any]) -> None:
    """Write checkpoint dict to disk."""
    path = _checkpoint_path(wiki_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cp, f, sort_keys=False, allow_unicode=True, default_flow_style=False)


def update_paper_statuses(
    wiki_root,
    results: dict[str, tuple[str, str | None]],
    wave_commit_sha: str,
) -> None:
    """Update paper statuses from subagent results and bump wave counter.

    results: {paper_id: ("ok"|"failed", error_message_or_None)}
    """
    cp = read_checkpoint(wiki_root)
    if cp is None:
        raise FileNotFoundError("No checkpoint found")
    for pid, (status, error) in results.items():
        cp["papers"][pid] = status
        if error:
            cp["errors"][pid] = error
    cp["last-completed-wave"] += 1
    cp["wave-commits"].append(wave_commit_sha)
    write_checkpoint(wiki_root, cp)


def is_stale(wiki_root) -> bool:
    """True if checkpoint exists and is older than STALE_THRESHOLD."""
    cp = read_checkpoint(wiki_root)
    if cp is None:
        return False
    try:
        run_time = datetime.fromisoformat(cp["run-id"].replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - run_time > STALE_THRESHOLD
    except (KeyError, ValueError):
        return True


def delete_checkpoint(wiki_root) -> None:
    """Delete the checkpoint file if it exists."""
    path = _checkpoint_path(wiki_root)
    if path.exists():
        path.unlink()


def get_pending_papers(wiki_root) -> list[str]:
    """Return paper-ids that are still pending or failed (for retry)."""
    cp = read_checkpoint(wiki_root)
    if cp is None:
        return []
    return [pid for pid, status in cp["papers"].items() if status in ("pending", "failed")]
