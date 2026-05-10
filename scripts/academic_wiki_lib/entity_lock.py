"""Per-entity OS file lock for atomic read-modify-write on shared wiki pages.

Uses the filelock library so the same code path works on POSIX (fcntl.flock)
and Windows (msvcrt.locking). Both primitives auto-release the lock when the
holding process dies, so stale locks are not normally possible. If a process
is wedged but alive, the user clears <wiki_root>/.locks/ manually before retrying.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

VALID_KINDS = frozenset({"paper", "concept", "method", "open-problem", "venue", "reports"})


def _lock_path(wiki_root, kind: str, key: str) -> Path:
    return Path(os.fspath(wiki_root)) / ".locks" / kind / f"{key}.lock"


@contextmanager
def acquire(wiki_root, kind: str, key: str, timeout_seconds: float = 60.0):
    """Acquire exclusive OS file lock on <wiki_root>/.locks/<kind>/<key>.lock.

    Raises ValueError if kind is not one of VALID_KINDS.
    Raises TimeoutError if the lock cannot be acquired within timeout_seconds.
    """
    if kind not in VALID_KINDS:
        raise ValueError(
            f"Unknown entity lock kind: {kind!r} (expected one of {sorted(VALID_KINDS)})"
        )
    path = _lock_path(wiki_root, kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path), timeout=timeout_seconds)
    try:
        lock.acquire()
    except Timeout:
        raise TimeoutError(
            f"Could not acquire entity lock {kind}/{key} within {timeout_seconds}s"
        ) from None
    try:
        yield
    finally:
        lock.release()
