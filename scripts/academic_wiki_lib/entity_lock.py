"""Per-entity fcntl.flock helper for atomic read-modify-write on shared wiki pages."""
from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path

VALID_KINDS = frozenset({"paper", "concept", "method", "open-problem", "venue", "reports"})
POLL_INTERVAL_S = 0.1


def _lock_path(wiki_root, kind: str, key: str) -> Path:
    return Path(os.fspath(wiki_root)) / ".locks" / kind / f"{key}.lock"


@contextmanager
def acquire(wiki_root, kind: str, key: str, timeout_seconds: float = 60.0):
    """Acquire exclusive fcntl.flock on <wiki_root>/.locks/<kind>/<key>.lock.

    Raises ValueError if kind is not one of VALID_KINDS.
    Raises TimeoutError if the lock cannot be acquired within timeout_seconds.

    The lock auto-releases when this process dies (crash or clean), so stale
    locks are not normally possible. If a process is wedged but alive, the
    user clears <wiki_root>/.locks/ manually before retrying.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown entity lock kind: {kind!r} (expected one of {sorted(VALID_KINDS)})")

    path = _lock_path(wiki_root, kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire entity lock {kind}/{key} within {timeout_seconds}s"
                    ) from None
                time.sleep(POLL_INTERVAL_S)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
