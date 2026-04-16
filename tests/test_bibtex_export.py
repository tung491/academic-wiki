"""Tests for bibtex-export.py per spec §5.6."""
import subprocess
from pathlib import Path

from academic_wiki_lib.frontmatter import write_frontmatter

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "bibtex-export.py")


def _setup_paper(wiki_root, pid, tags, created, bib_content=None):
    """Write a paper page + its .bib file."""
    write_frontmatter(
        str(wiki_root / "wiki/papers" / f"{pid}.md"),
        {
            "paper-id": pid, "type": "paper", "status": "read",
            "created": created, "updated": created,
            "title": f"{pid} title", "authors": [{"slug": "x", "name": "X"}],
            "year": 2020, "identifiers": {},
            "source-version": "",
            "bib-file": f"raw/bib/{pid}.bib",
            "extract": f"raw/extracts/{pid}.md",
            "references-raw": [], "cites": [],
            "tags": tags,
        },
        "body\n",
    )
    if bib_content is None:
        bib_content = f"@misc{{{pid},}}\n"
    (wiki_root / "raw/bib" / f"{pid}.bib").write_text(bib_content)


def _run(*args, wiki_root):
    result = subprocess.run(
        ["python3", SCRIPT, str(wiki_root), *args],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_export_by_field(tmp_wiki):
    _setup_paper(tmp_wiki, "a-2020-one", ["field/nlp"], "2024-01-01")
    _setup_paper(tmp_wiki, "b-2021-two", ["field/nlp"], "2024-06-01")
    _setup_paper(tmp_wiki, "c-2022-three", ["field/wireless"], "2024-03-01")
    rc, out, _ = _run("--field", "nlp", wiki_root=tmp_wiki)
    assert rc == 0
    bib_files = list((tmp_wiki / "outputs/bib").glob("*.bib"))
    assert len(bib_files) == 1
    content = bib_files[0].read_text()
    assert "a-2020-one" in content
    assert "b-2021-two" in content
    assert "c-2022-three" not in content


def test_export_by_project(tmp_wiki):
    _setup_paper(tmp_wiki, "a", ["field/nlp", "project/survey-2025"], "2024-01-01")
    _setup_paper(tmp_wiki, "b", ["field/nlp"], "2024-01-01")
    rc, out, _ = _run("--project", "survey-2025", wiki_root=tmp_wiki)
    assert rc == 0
    content = list((tmp_wiki / "outputs/bib").glob("*.bib"))[0].read_text()
    assert "@misc{a," in content
    assert "@misc{b," not in content


def test_export_by_tag(tmp_wiki):
    _setup_paper(tmp_wiki, "a", ["field/nlp", "user/must-cite"], "2024-01-01")
    _setup_paper(tmp_wiki, "b", ["field/nlp"], "2024-01-01")
    rc, out, _ = _run("--tag", "user/must-cite", wiki_root=tmp_wiki)
    assert rc == 0
    content = list((tmp_wiki / "outputs/bib").glob("*.bib"))[0].read_text()
    assert "@misc{a," in content
    assert "@misc{b," not in content


def test_export_by_keys_explicit(tmp_wiki):
    _setup_paper(tmp_wiki, "a", ["field/nlp"], "2024-01-01")
    _setup_paper(tmp_wiki, "b", ["field/nlp"], "2024-01-01")
    _setup_paper(tmp_wiki, "c", ["field/nlp"], "2024-01-01")
    rc, out, _ = _run("--keys", "a,c", wiki_root=tmp_wiki)
    assert rc == 0
    content = list((tmp_wiki / "outputs/bib").glob("*.bib"))[0].read_text()
    assert "@misc{a," in content
    assert "@misc{c," in content
    assert "@misc{b," not in content


def test_export_and_semantics_combined(tmp_wiki):
    """Multiple selectors combine with AND."""
    _setup_paper(tmp_wiki, "a", ["field/nlp", "project/survey"], "2024-01-01")
    _setup_paper(tmp_wiki, "b", ["field/nlp"], "2024-01-01")
    _setup_paper(tmp_wiki, "c", ["project/survey"], "2024-01-01")
    rc, out, _ = _run("--field", "nlp", "--project", "survey", wiki_root=tmp_wiki)
    assert rc == 0
    content = list((tmp_wiki / "outputs/bib").glob("*.bib"))[0].read_text()
    # Only "a" has BOTH field/nlp AND project/survey
    assert "@misc{a," in content
    assert "@misc{b," not in content
    assert "@misc{c," not in content


def test_export_since(tmp_wiki):
    _setup_paper(tmp_wiki, "a", ["field/nlp"], "2023-06-01")
    _setup_paper(tmp_wiki, "b", ["field/nlp"], "2024-06-01")
    rc, out, _ = _run("--field", "nlp", "--since", "2024-01-01", wiki_root=tmp_wiki)
    assert rc == 0
    content = list((tmp_wiki / "outputs/bib").glob("*.bib"))[0].read_text()
    assert "@misc{b," in content
    assert "@misc{a," not in content


def test_label_override(tmp_wiki):
    _setup_paper(tmp_wiki, "a", ["field/nlp"], "2024-01-01")
    rc, out, _ = _run("--field", "nlp", "--label", "my-export", wiki_root=tmp_wiki)
    assert rc == 0
    files = list((tmp_wiki / "outputs/bib").glob("*my-export*.bib"))
    assert len(files) == 1


def test_label_resolution_priority_project_beats_field(tmp_wiki):
    """With both --project and --field, label uses project per spec priority."""
    _setup_paper(tmp_wiki, "a", ["field/nlp", "project/survey"], "2024-01-01")
    rc, out, _ = _run("--field", "nlp", "--project", "survey", wiki_root=tmp_wiki)
    assert rc == 0
    files = list((tmp_wiki / "outputs/bib").glob("*survey*.bib"))
    assert len(files) == 1, "filename should be derived from --project (higher priority than --field)"


def test_reports_bib_incomplete(tmp_wiki):
    _setup_paper(
        tmp_wiki, "a", ["field/nlp"], "2024-01-01",
        bib_content="% bib-incomplete: true\n@misc{a,}\n",
    )
    _setup_paper(tmp_wiki, "b", ["field/nlp"], "2024-01-01")
    rc, out, _ = _run("--field", "nlp", wiki_root=tmp_wiki)
    assert rc == 0
    assert "incomplete" in out.lower() or "bib-incomplete" in out.lower()


def test_missing_bib_file_reported(tmp_wiki):
    """A paper page whose bib file is absent on disk is reported as missing."""
    _setup_paper(tmp_wiki, "a", ["field/nlp"], "2024-01-01")
    # Delete the bib file
    (tmp_wiki / "raw/bib/a.bib").unlink()
    rc, out, _ = _run("--field", "nlp", wiki_root=tmp_wiki)
    # May exit 1 (no papers with usable bib) or 0 (empty export) — check incomplete reporting
    assert "missing" in out.lower() or "incomplete" in out.lower()


def test_no_selector_fails(tmp_wiki):
    """No selector argument → error with non-zero exit."""
    _setup_paper(tmp_wiki, "a", ["field/nlp"], "2024-01-01")
    rc, out, err = _run(wiki_root=tmp_wiki)
    assert rc != 0


def test_no_matches_exits_1(tmp_wiki):
    """No papers match the selector → exit 1 with message."""
    _setup_paper(tmp_wiki, "a", ["field/wireless"], "2024-01-01")
    rc, out, _ = _run("--field", "nonexistent", wiki_root=tmp_wiki)
    assert rc != 0
    assert "no papers" in out.lower() or "no match" in out.lower()


def test_output_filename_has_date(tmp_wiki):
    """Output filename starts with YYYY-MM-DD-<label>."""
    _setup_paper(tmp_wiki, "a", ["field/nlp"], "2024-01-01")
    from datetime import date
    rc, out, _ = _run("--field", "nlp", wiki_root=tmp_wiki)
    today = date.today().isoformat()
    files = list((tmp_wiki / "outputs/bib").glob(f"{today}-*.bib"))
    assert len(files) == 1
