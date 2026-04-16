"""Advisory lockfile for mutating operations per spec §8.1."""
from __future__ import annotations

import os
import warnings
from datetime import datetime, timezone


class LockHeld(Exception):
    """Raised when the lock is held by a live process."""


class StaleLockRecovered(UserWarning):
    """Warned when an existing lock was stale (holder pid is gone) and got recovered."""


def _is_alive(pid: int) -> bool:
    """Return True if pid is a live process on this system."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but we don't own it; treat as alive.
        return True
    return True


def acquire(lock_path, op: str) -> None:
    """Acquire the lock. Raises LockHeld if held by a live process.

    Accepts str or os.PathLike for lock_path.
    """
    path = os.fspath(lock_path)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                content = f.read().strip()
            parts = content.split(":", 2)
            if len(parts) >= 1 and parts[0]:
                try:
                    pid = int(parts[0])
                except ValueError:
                    pid = -1
                if pid > 0 and _is_alive(pid):
                    ts = parts[1] if len(parts) >= 2 else "unknown"
                    existing_op = parts[2] if len(parts) >= 3 else "unknown"
                    raise LockHeld(
                        f"Another operation is in progress: {existing_op} started at {ts} by pid {pid}"
                    )
                else:
                    warnings.warn(
                        f"Stale lock (pid {parts[0]}) — recovering",
                        StaleLockRecovered,
                    )
            else:
                warnings.warn(
                    f"Malformed lock file at {path} — recovering",
                    StaleLockRecovered,
                )
        except OSError as e:
            warnings.warn(
                f"Could not read lock file at {path} — recovering: {e}",
                StaleLockRecovered,
            )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    with open(path, "w") as f:
        f.write(f"{os.getpid()}:{ts}:{op}")


def release(lock_path) -> None:
    """Release the lock. No-op if absent."""
    try:
        os.remove(os.fspath(lock_path))
    except FileNotFoundError:
        pass
