"""Integration tests for scripts/migrate-venues.py invoked via subprocess."""
import hashlib
import subprocess
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import write_frontmatter

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "migrate-venues.py")


def run_migrate(wiki_path, *args):
    return subprocess.run(
        ["python3", SCRIPT, "--wiki-path", str(wiki_path), *args],
        capture_output=True, text=True,
    )


def _venue(wiki, slug, name, papers=None, venue_type="conference"):
    fm = {
        "type": "venue", "name": name, "slug": slug, "venue-type": venue_type,
        "created": "2026-04-01", "updated": "2026-04-01",
        "papers": list(papers or []), "tags": [],
    }
    write_frontmatter(str(wiki / "wiki/venues" / f"{slug}.md"), fm, "Body of " + slug + "\n")


def _dirhash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_dry_run_writes_report_and_changes_nothing_else(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    # Commit the venue page so the working tree is clean
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "venue"], cwd=tmp_git_wiki, check=True)

    # Hash everything that should be untouched by dry-run (excludes outputs/, where
    # the report lands, and .lock which the script transiently creates).
    wiki_dir_hash_before = _dirhash(tmp_git_wiki / "wiki")

    result = run_migrate(tmp_git_wiki, "--dry-run")
    assert result.returncode == 0, result.stderr

    # Report file written
    reports = list((tmp_git_wiki / "outputs" / "reports").glob("*-venue-migration.md"))
    assert len(reports) == 1, f"expected 1 report, got: {reports}"
    report = reports[0].read_text()
    assert "asilomar-conference-on-signals-systems-and-computers" in report
    assert "Renames" in report

    # Wiki tree byte-identical (no rename, no frontmatter mutation, no body edit).
    assert _dirhash(tmp_git_wiki / "wiki") == wiki_dir_hash_before

    # The venue file was not renamed (--dry-run is read-only)
    assert (tmp_git_wiki / "wiki/venues/2022-56th-asilomar-conference-on-signals-systems-and-computers.md").exists()
    assert not (tmp_git_wiki / "wiki/venues/asilomar-conference-on-signals-systems-and-computers.md").exists()


def test_default_is_dry_run(tmp_git_wiki):
    """No --dry-run / --apply flag → defaults to --dry-run."""
    _venue(tmp_git_wiki, "2024-aina", "2024 AINA", papers=["p"])
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "venue"], cwd=tmp_git_wiki, check=True)
    result = run_migrate(tmp_git_wiki)
    assert result.returncode == 0, result.stderr
    # Old page still exists; canonical does not exist
    assert (tmp_git_wiki / "wiki/venues/2024-aina.md").exists()
    assert not (tmp_git_wiki / "wiki/venues/aina.md").exists()


def test_lock_held_aborts(tmp_git_wiki):
    """If .lock is held by a live pid, both --dry-run and --apply fail before doing any work."""
    import os
    # Create a lock with our own pid
    (tmp_git_wiki / ".lock").write_text(f"{os.getpid()}:2026-05-10T000000Z:other")

    dry = run_migrate(tmp_git_wiki, "--dry-run")
    assert dry.returncode != 0
    assert "lock" in (dry.stderr + dry.stdout).lower()

    apply_ = run_migrate(tmp_git_wiki, "--apply")
    assert apply_.returncode != 0
    assert "lock" in (apply_.stderr + apply_.stdout).lower()


def test_apply_single_page_rename(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "venue"], cwd=tmp_git_wiki, check=True)

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr

    old_path = tmp_git_wiki / "wiki/venues/2022-56th-asilomar-conference-on-signals-systems-and-computers.md"
    new_path = tmp_git_wiki / "wiki/venues/asilomar-conference-on-signals-systems-and-computers.md"
    assert not old_path.exists(), "old slug file should be removed"
    assert new_path.exists(), "canonical slug file should exist"

    from academic_wiki_lib.frontmatter import read_frontmatter
    fm, body = read_frontmatter(new_path)
    assert fm["slug"] == "asilomar-conference-on-signals-systems-and-computers"
    assert fm["name"] == "Asilomar Conference on Signals, Systems, and Computers"
    # Old slug recorded as alias
    assert "2022-56th-asilomar-conference-on-signals-systems-and-computers" in fm.get("aliases", [])
    # Body of original page preserved
    assert "Body of 2022-56th-asilomar" in body
