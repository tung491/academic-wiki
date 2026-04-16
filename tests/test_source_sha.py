"""Tests for source-file SHA-256 helper."""
from academic_wiki_lib.source_sha import file_sha256


def test_sha_of_known_content(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_bytes(b"hello world")
    # SHA-256 of "hello world" is b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
    assert file_sha256(str(f)) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_sha_is_deterministic(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"\x00\x01\x02\x03" * 1024)
    assert file_sha256(str(f)) == file_sha256(str(f))


def test_sha_differs_for_different_content(tmp_path):
    a = tmp_path / "a.txt"
    a.write_bytes(b"alpha")
    b = tmp_path / "b.txt"
    b.write_bytes(b"beta")
    assert file_sha256(str(a)) != file_sha256(str(b))


def test_sha_handles_large_file(tmp_path):
    """Full end-to-end: 5MB file hash matches an independent hashlib calculation."""
    import hashlib
    payload = b"x" * (5 * 1024 * 1024)
    f = tmp_path / "big.bin"
    f.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert file_sha256(str(f)) == expected


def test_sha_correct_across_chunk_boundaries(tmp_path):
    """Files at sizes straddling the internal chunk size must hash identically
    to a single-shot hashlib.sha256 — proves chunked streaming doesn't lose bytes."""
    import hashlib
    chunk = 64 * 1024
    for size in (chunk - 1, chunk, chunk + 1, 3 * chunk, 3 * chunk + 17):
        payload = bytes((i * 31) & 0xFF for i in range(size))  # pseudo-varied content
        f = tmp_path / f"size-{size}.bin"
        f.write_bytes(payload)
        expected = hashlib.sha256(payload).hexdigest()
        actual = file_sha256(str(f))
        assert actual == expected, f"Mismatch at size {size}"


def test_sha_of_empty_file(tmp_path):
    """An empty file has a well-known SHA-256."""
    f = tmp_path / "empty.txt"
    f.write_bytes(b"")
    # SHA-256 of empty input is e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    assert file_sha256(str(f)) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha_accepts_pathlib_path(tmp_path):
    """file_sha256 should accept pathlib.Path (not only str) since callers use Path."""
    f = tmp_path / "ok.txt"
    f.write_bytes(b"content")
    # Pass Path directly, not str(Path). Must not raise.
    from pathlib import Path
    # Use os.fspath or rely on file_sha256 handling Path — spec: accept any os.PathLike
    result = file_sha256(Path(str(f)))
    assert len(result) == 64


def test_sha_raises_on_missing_file(tmp_path):
    import pytest
    with pytest.raises((FileNotFoundError, OSError)):
        file_sha256(str(tmp_path / "does-not-exist.bin"))
