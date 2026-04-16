"""SHA-256 helper for source-file deduplication."""
from __future__ import annotations

import hashlib
import os

_CHUNK = 64 * 1024


def file_sha256(path) -> str:
    """Return the hex-encoded SHA-256 of the file at path.

    Accepts str or any os.PathLike. Raises FileNotFoundError if the file doesn't exist.
    """
    h = hashlib.sha256()
    with open(os.fspath(path), "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
