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


def test_apply_multi_page_merge(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pA", "pB"])
    _venue(tmp_git_wiki, "2023-57th-asilomar-conference-on-signals-systems-and-computers",
           "2023 57th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pC"])
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "venues"], cwd=tmp_git_wiki, check=True)

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr

    canon = tmp_git_wiki / "wiki/venues/asilomar-conference-on-signals-systems-and-computers.md"
    assert canon.exists()
    assert not (tmp_git_wiki / "wiki/venues/2022-56th-asilomar-conference-on-signals-systems-and-computers.md").exists()
    assert not (tmp_git_wiki / "wiki/venues/2023-57th-asilomar-conference-on-signals-systems-and-computers.md").exists()

    from academic_wiki_lib.frontmatter import read_frontmatter
    fm, body = read_frontmatter(canon)
    assert fm["slug"] == "asilomar-conference-on-signals-systems-and-computers"
    assert fm["name"] == "Asilomar Conference on Signals, Systems, and Computers"
    assert sorted(fm["papers"]) == ["pA", "pB", "pC"]
    # Both old slugs are aliases
    assert "2022-56th-asilomar-conference-on-signals-systems-and-computers" in fm["aliases"]
    assert "2023-57th-asilomar-conference-on-signals-systems-and-computers" in fm["aliases"]
    # Both source bodies archived
    assert "## Merged from" in body
    assert "Body of 2022-56th-asilomar" in body
    assert "Body of 2023-57th-asilomar" in body


def test_apply_merge_with_existing_canonical_preserves_body(tmp_git_wiki):
    """Pre-existing canonical page's body is preserved in 'Merged from'."""
    _venue(tmp_git_wiki, "asilomar-conference-on-signals-systems-and-computers",
           "Asilomar Conference on Signals, Systems, and Computers", papers=["pX"])
    _venue(tmp_git_wiki, "2024-58th-asilomar-conference-on-signals-systems-and-computers",
           "2024 58th Asilomar Conference on Signals, Systems, and Computers", papers=["pY"])
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "venues"], cwd=tmp_git_wiki, check=True)

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr

    canon = tmp_git_wiki / "wiki/venues/asilomar-conference-on-signals-systems-and-computers.md"
    from academic_wiki_lib.frontmatter import read_frontmatter
    fm, body = read_frontmatter(canon)
    # Both bodies preserved (the canonical page's prior body and the new member's body)
    assert "Body of asilomar-conference" in body
    assert "Body of 2024-58th-asilomar" in body
    assert sorted(fm["papers"]) == ["pX", "pY"]
    # Non-canonical member is recorded as an alias; canonical slug is not in its own aliases.
    assert "2024-58th-asilomar-conference-on-signals-systems-and-computers" in fm["aliases"]
    assert "asilomar-conference-on-signals-systems-and-computers" not in fm.get("aliases", [])


def _paper(wiki, paper_id, venue_slug, extra_tags=()):
    fm = {
        "paper-id": paper_id, "type": "paper", "status": "read",
        "created": "2024-01-01", "updated": "2024-01-01",
        "title": "T", "authors": [], "year": 2024,
        "venue": venue_slug, "identifiers": {}, "aliases": [],
        "bib-file": "x", "extract": "x", "references-raw": [], "cites": [],
        "tags": [f"venue/{venue_slug}", *extra_tags],
    }
    write_frontmatter(str(wiki / "wiki/papers" / f"{paper_id}.md"), fm, "Body.\n")


def test_apply_rewrites_paper_pages(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    _paper(tmp_git_wiki, "pA",
           "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           extra_tags=["field/wireless-comms"])
    _paper(tmp_git_wiki, "pUnaffected", "ieee-transactions-on-communications")
    # Need the unaffected venue too for lint cleanliness, though migration doesn't require it
    _venue(tmp_git_wiki, "ieee-transactions-on-communications",
           "IEEE Transactions on Communications", papers=["pUnaffected"])

    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_git_wiki, check=True)

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr

    from academic_wiki_lib.frontmatter import read_frontmatter
    fm_a, _ = read_frontmatter(tmp_git_wiki / "wiki/papers/pA.md")
    assert fm_a["venue"] == "asilomar-conference-on-signals-systems-and-computers"
    assert "venue/asilomar-conference-on-signals-systems-and-computers" in fm_a["tags"]
    assert "venue/2022-56th-asilomar-conference-on-signals-systems-and-computers" not in fm_a["tags"]
    assert "field/wireless-comms" in fm_a["tags"]  # unrelated tags preserved
    assert str(fm_a["updated"]) == _today_iso()  # bumped

    # Unaffected paper's venue is unchanged.
    fm_u, _ = read_frontmatter(tmp_git_wiki / "wiki/papers/pUnaffected.md")
    assert fm_u["venue"] == "ieee-transactions-on-communications"


def test_apply_rewrites_paper_with_both_old_and_new_venue_tags(tmp_git_wiki):
    """A partially-migrated paper (already has venue/new tag too) is deduped."""
    old_slug = "2022-56th-asilomar-conference-on-signals-systems-and-computers"
    new_slug = "asilomar-conference-on-signals-systems-and-computers"
    _venue(tmp_git_wiki, old_slug,
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pPartial"])
    fm = {
        "paper-id": "pPartial", "type": "paper", "status": "read",
        "created": "2024-01-01", "updated": "2024-01-01",
        "title": "T", "authors": [], "year": 2024,
        "venue": old_slug, "identifiers": {}, "aliases": [],
        "bib-file": "x", "extract": "x", "references-raw": [], "cites": [],
        "tags": [f"venue/{old_slug}", f"venue/{new_slug}", "field/x"],
    }
    write_frontmatter(str(tmp_git_wiki / "wiki/papers/pPartial.md"), fm, "Body.\n")
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_git_wiki, check=True)

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr

    from academic_wiki_lib.frontmatter import read_frontmatter
    fm_p, _ = read_frontmatter(tmp_git_wiki / "wiki/papers/pPartial.md")
    assert fm_p["tags"].count(f"venue/{new_slug}") == 1, "venue/new should appear exactly once"
    assert f"venue/{old_slug}" not in fm_p["tags"]
    assert "field/x" in fm_p["tags"]


def test_apply_rewrites_paper_with_no_venue_tag(tmp_git_wiki):
    """A paper with venue: but no venue/* tag still gets the new venue/* tag appended."""
    old_slug = "2022-56th-asilomar-conference-on-signals-systems-and-computers"
    new_slug = "asilomar-conference-on-signals-systems-and-computers"
    _venue(tmp_git_wiki, old_slug,
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pNoTag"])
    fm = {
        "paper-id": "pNoTag", "type": "paper", "status": "read",
        "created": "2024-01-01", "updated": "2024-01-01",
        "title": "T", "authors": [], "year": 2024,
        "venue": old_slug, "identifiers": {}, "aliases": [],
        "bib-file": "x", "extract": "x", "references-raw": [], "cites": [],
        "tags": ["field/x"],  # no venue/* tag at all
    }
    write_frontmatter(str(tmp_git_wiki / "wiki/papers/pNoTag.md"), fm, "Body.\n")
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_git_wiki, check=True)

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr

    from academic_wiki_lib.frontmatter import read_frontmatter
    fm_p, _ = read_frontmatter(tmp_git_wiki / "wiki/papers/pNoTag.md")
    assert f"venue/{new_slug}" in fm_p["tags"]
    assert "field/x" in fm_p["tags"]


def _today_iso():
    from datetime import date
    return date.today().isoformat()


def test_apply_refuses_dirty_tree(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    # Don't commit — leave the tree dirty
    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode != 0
    assert "dirty" in (result.stderr + result.stdout).lower() or "uncommitted" in (result.stderr + result.stdout).lower()
    # The lock should have been released
    assert not (tmp_git_wiki / ".lock").exists()


def test_apply_aborts_on_skipped_pages(tmp_git_wiki):
    """If any venue page has unparseable frontmatter, --apply aborts."""
    bad = tmp_git_wiki / "wiki/venues/broken.md"
    bad.write_text("---\nbroken: [\n---\nx\n")
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "broken"], cwd=tmp_git_wiki, check=True)
    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode != 0
    assert "skipped" in (result.stderr + result.stdout).lower() or "could not" in (result.stderr + result.stdout).lower()
    # No snapshot tag should have been created
    tags = subprocess.run(["git", "tag", "-l"], cwd=tmp_git_wiki,
                          capture_output=True, text=True).stdout.split()
    assert not any(t.startswith("snapshot/pre-venue-migration-") for t in tags)
    # The report should still be written so the user can inspect it
    reports = list((tmp_git_wiki / "outputs" / "reports").glob("*-venue-migration.md"))
    assert len(reports) == 1, "report should be written even on skipped-abort"
    # Working tree should be left clean — the abort committed the report so a
    # subsequent --apply doesn't see it as untracked.
    porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=tmp_git_wiki,
                               capture_output=True, text=True).stdout.strip()
    # Filter out advisory lock entries that may transiently appear.
    leftover = [line for line in porcelain.splitlines() if not line.endswith(".lock")]
    assert leftover == [], f"working tree not clean after abort: {leftover!r}"


def test_apply_creates_snapshot_tag(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "venue"], cwd=tmp_git_wiki, check=True)

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr
    tags = subprocess.run(["git", "tag", "-l"], cwd=tmp_git_wiki,
                          capture_output=True, text=True).stdout.split()
    assert any(t.startswith("snapshot/pre-venue-migration-") for t in tags)


def test_apply_writes_log_and_single_commit(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "venue"], cwd=tmp_git_wiki, check=True)
    head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_git_wiki,
                                 capture_output=True, text=True).stdout.strip()

    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode == 0, result.stderr

    head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_git_wiki,
                                capture_output=True, text=True).stdout.strip()
    assert head_after != head_before
    # Exactly one commit was added
    rev_list = subprocess.run(["git", "rev-list", f"{head_before}..HEAD"],
                              cwd=tmp_git_wiki, capture_output=True, text=True).stdout.split()
    assert len(rev_list) == 1
    msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=tmp_git_wiki,
                         capture_output=True, text=True).stdout
    assert "migrate" in msg and "venue normalization" in msg
    # log.md got an entry
    log = (tmp_git_wiki / "log.md").read_text()
    assert "migrate-venues" in log


def test_apply_then_dry_run_reports_zero_changes(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    _venue(tmp_git_wiki, "2023-57th-asilomar-conference-on-signals-systems-and-computers",
           "2023 57th Asilomar Conference on Signals, Systems, and Computers", papers=["pB"])
    _paper(tmp_git_wiki, "pA",
           "2022-56th-asilomar-conference-on-signals-systems-and-computers")
    _paper(tmp_git_wiki, "pB",
           "2023-57th-asilomar-conference-on-signals-systems-and-computers")
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_git_wiki, check=True)

    # First --apply
    r1 = run_migrate(tmp_git_wiki, "--apply")
    assert r1.returncode == 0, r1.stderr

    # Now --dry-run again — plan should be empty
    r2 = run_migrate(tmp_git_wiki, "--dry-run")
    assert r2.returncode == 0, r2.stderr

    reports = sorted((tmp_git_wiki / "outputs" / "reports").glob("*-venue-migration.md"))
    assert reports
    latest = reports[-1].read_text()
    # No renames, no merges
    assert "0 renamed" in latest or "## Renames" not in latest
    assert "## Merges" not in latest


def test_apply_twice_is_no_op(tmp_git_wiki):
    """Re-running --apply after success makes no changes (no new commit)."""
    _venue(tmp_git_wiki, "2024-aina", "2024 AINA", papers=["pA"])
    _paper(tmp_git_wiki, "pA", "2024-aina")
    subprocess.run(["git", "add", "."], cwd=tmp_git_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_git_wiki, check=True)

    run_migrate(tmp_git_wiki, "--apply")
    head_after_first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_git_wiki,
                                      capture_output=True, text=True).stdout.strip()

    r = run_migrate(tmp_git_wiki, "--apply")
    assert r.returncode == 0, r.stderr
    head_after_second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_git_wiki,
                                       capture_output=True, text=True).stdout.strip()
    assert head_after_second == head_after_first, "second --apply should not add commits"
