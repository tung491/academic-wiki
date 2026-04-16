"""Advisory lockfile for mutating operations per spec §8.1."""
from __future__ import annotations

import errno
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


def _parse_lock_content(content: str) -> tuple[int | None, str, str]:
    """Parse '<pid>:<iso-timestamp>:<op>' robustly even if the timestamp has colons.

    Returns (pid_or_None, timestamp, op). pid_or_None is None if unparseable.
    """
    content = content.strip()
    if not content:
        return None, "", ""
    # Split off the pid (first segment before ':')
    pid_str, _, rest = content.partition(":")
    try:
        pid = int(pid_str)
    except ValueError:
        return None, "", ""
    # Split the remainder into (timestamp, op) using rsplit
    if ":" in rest:
        ts, _, op = rest.rpartition(":")
    else:
        ts, op = rest, ""
    return pid, ts, op


def acquire(lock_path, op: str) -> None:
    """Acquire the lock atomically. Raises LockHeld if held by a live process.

    Uses O_CREAT | O_EXCL for race-free creation. On conflict, reads the existing
    file: if the holder pid is alive, raises LockHeld; otherwise removes the stale
    lock (with a warning) and retries atomic creation.

    Accepts str or os.PathLike for lock_path.
    """
    path = os.fspath(lock_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    payload = f"{os.getpid()}:{ts}:{op}"

    # Retry loop in case of stale-lock recovery
    for attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, payload.encode("utf-8"))
            finally:
                os.close(fd)
            return
        except FileExistsError:
            # Someone holds the lock (or a stale one exists). Inspect.
            try:
                with open(path, "r") as f:
                    existing = f.read()
            except OSError as e:
                warnings.warn(
                    f"Could not read lock file at {path} — recovering: {e}",
                    StaleLockRecovered,
                )
                existing = ""

            pid, existing_ts, existing_op = _parse_lock_content(existing)

            if pid is not None and pid > 0 and _is_alive(pid):
                raise LockHeld(
                    f"Another operation is in progress: {existing_op or 'unknown'} "
                    f"started at {existing_ts or 'unknown'} by pid {pid}"
                )

            # Stale or malformed — warn, remove, retry
            if pid is None:
                warnings.warn(
                    f"Malformed lock file at {path} — recovering",
                    StaleLockRecovered,
                )
            else:
                warnings.warn(
                    f"Stale lock (pid {pid}) — recovering",
                    StaleLockRecovered,
                )
            try:
                os.remove(path)
            except FileNotFoundError:
                pass  # Another racer already cleared it
            # Fall through to retry

    # Two failed atomic creates in a row — something's racing. Give up.
    raise LockHeld(f"Could not acquire lock at {path} after 2 attempts (race detected)")


def release(lock_path) -> None:
    """Release the lock. No-op if absent."""
    try:
        os.remove(os.fspath(lock_path))
    except FileNotFoundError:
        pass
