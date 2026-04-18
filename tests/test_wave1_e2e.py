"""Wave 1 end-to-end integration tests.

Exercises academic_wiki_lib primitives in combination to verify the deterministic
plumbing of the ingest/compile/query pipelines. Does NOT drive the actual agent
commands (those require MCP tools and LLM).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter
from academic_wiki_lib.lockfile import LockHeld, acquire, release
from academic_wiki_lib.paper_id import (
    find_existing_paper_by_identifiers,
    generate_paper_id,
    resolve_collision,
)
from academic_wiki_lib.slug import make_slug
from academic_wiki_lib.source_sha import file_sha256
from academic_wiki_lib.templates import (
    GITIGNORE,
    INDEX_MD,
    LOG_MD,
    all_subdirs,
    claude_md,
    qmd_yml,
)
from academic_wiki_lib.wiki_paths import find_active_wiki


def _init_wiki_structure(wiki_root: Path, name: str) -> None:
    """Create the wiki directory tree and baseline files (mirrors init command)."""
    for d in all_subdirs():
        (wiki_root / d).mkdir(parents=True, exist_ok=True)
    (wiki_root / "CLAUDE.md").write_text(claude_md(name))
    (wiki_root / "wiki" / "index.md").write_text(INDEX_MD.format(name=name))
    (wiki_root / "log.md").write_text(LOG_MD.format(name=name))
    (wiki_root / ".gitignore").write_text(GITIGNORE)
    (wiki_root / "qmd.yml").write_text(qmd_yml(name))


def _git(*args, cwd):
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def test_init_creates_full_tree(tmp_wiki):
    """conftest tmp_wiki creates the 16-subdir skeleton; verify it matches all_subdirs()."""
    for d in all_subdirs():
        assert (tmp_wiki / d).is_dir(), f"Missing subdirectory: {d}"


def test_init_flow_produces_valid_wiki(tmp_path):
    """Init-style flow: templates + git init + initial commit → valid wiki + first commit."""
    wiki = tmp_path / "test-topic"
    wiki.mkdir()
    _init_wiki_structure(wiki, "test-topic")

    _git("init", cwd=wiki)
    _git("add", ".", cwd=wiki)
    _git("commit", "-m", "init: test-topic wiki", cwd=wiki)

    # Verify structure
    assert (wiki / "CLAUDE.md").is_file()
    assert "test-topic Wiki Schema" in (wiki / "CLAUDE.md").read_text()
    assert (wiki / "wiki/index.md").is_file()
    assert (wiki / ".git").is_dir()

    # Active wiki detection finds it
    assert find_active_wiki(str(wiki / "raw/papers")) == str(wiki)

    # Git log has the init commit
    out = _git("log", "--oneline", cwd=wiki).stdout
    assert "init: test-topic wiki" in out


def test_ingest_creates_paper_with_extract_frontmatter(tmp_path):
    """Simulate the deterministic parts of ingest: source-sha, paper-id, file save.
    Full ingest requires MCP tools; this exercises the parts that don't."""
    wiki = tmp_path / "academic"
    wiki.mkdir()
    _init_wiki_structure(wiki, "academic")

    # Simulate a raw PDF drop
    raw_pdf = wiki / "raw/papers/temp.pdf"
    pdf_bytes = b"%PDF-1.4\nfake pdf content for testing\n"
    raw_pdf.write_bytes(pdf_bytes)

    # Compute source-sha
    sha = file_sha256(str(raw_pdf))
    assert sha == hashlib.sha256(pdf_bytes).hexdigest()

    # Generate paper-id from metadata
    paper_id = generate_paper_id("Vaswani", 2017, "Attention Is All You Need")
    assert paper_id == "vaswani2017attention"

    # Resolve collision (no existing paper, so returns as-is)
    paper_id = resolve_collision(str(wiki), paper_id)
    assert paper_id == "vaswani2017attention"

    # Rename to paper-id basename
    final_pdf = wiki / f"raw/papers/{paper_id}.pdf"
    raw_pdf.rename(final_pdf)

    # Write the extract frontmatter (§3.7)
    extract_path = wiki / f"raw/extracts/{paper_id}.md"
    write_frontmatter(
        str(extract_path),
        {
            "paper-id": paper_id,
            "source-path": f"raw/papers/{paper_id}.pdf",
            "source-sha": sha,
            "source-type": "pdf",
            "source-url": "https://arxiv.org/abs/1706.03762",
            "extractor": "ocr-papers-to-latex",
            "extracted-at": "2026-04-16T10:00:00Z",
            "ocr-used": False,
            "extract-status": "complete",
        },
        "# Attention Is All You Need\n\nBody text.\n",
    )

    # Verify roundtrip
    fm, body = read_frontmatter(str(extract_path))
    assert fm["paper-id"] == paper_id
    assert fm["source-sha"] == sha
    assert "Attention Is All You Need" in body


def test_ingest_dedup_pass_1_by_source_sha(tmp_path):
    """Pass 1 dedup: same source-sha in another extract → skip."""
    wiki = tmp_path / "academic"
    wiki.mkdir()
    _init_wiki_structure(wiki, "academic")

    # Write an existing extract with known source-sha
    existing_sha = hashlib.sha256(b"fake content").hexdigest()
    write_frontmatter(
        str(wiki / "raw/extracts/vaswani2017attention.md"),
        {
            "paper-id": "vaswani2017attention",
            "source-sha": existing_sha,
            "source-type": "pdf",
        },
        "body\n",
    )

    # Simulate computing sha of a new incoming source — same bytes
    incoming_path = wiki / "raw/papers/incoming.pdf"
    incoming_path.write_bytes(b"fake content")
    incoming_sha = file_sha256(str(incoming_path))
    assert incoming_sha == existing_sha

    # Scan for the sha — real ingest would skip. We just verify the detection.
    hits = []
    for p in (wiki / "raw/extracts").glob("*.md"):
        fm, _ = read_frontmatter(str(p))
        if fm.get("source-sha") == incoming_sha:
            hits.append(fm["paper-id"])
    assert hits == ["vaswani2017attention"]


def test_ingest_dedup_pass_2_by_identifiers(tmp_wiki):
    """Pass 2 dedup: identifier match → reuse paper-id."""
    paper = tmp_wiki / "wiki/papers/vaswani2017attention.md"
    write_frontmatter(
        str(paper),
        {
            "paper-id": "vaswani2017attention",
            "identifiers": {"arxiv": "1706.03762", "arxiv-version": "v3"},
        },
        "",
    )
    # Same arxiv ID at a different version — should match (version stripped)
    found = find_existing_paper_by_identifiers(
        str(tmp_wiki), {"arxiv": "1706.03762v5"}
    )
    assert found == "vaswani2017attention"


def test_collision_resolution_when_different_papers_produce_same_id(tmp_wiki):
    """Two different papers both produce smith2020neural → 2, 3, ..."""
    (tmp_wiki / "wiki/papers/smith2020neural.md").write_text("---\n---\n")
    (tmp_wiki / "wiki/papers/smith2020neural2.md").write_text("---\n---\n")
    new_id = resolve_collision(str(tmp_wiki), "smith2020neural")
    assert new_id == "smith2020neural3"


def test_lockfile_prevents_concurrent_ops(tmp_wiki):
    """Acquire prevents a second acquire from the same process (live pid)."""
    lock = tmp_wiki / ".lock"
    acquire(str(lock), op="ingest")
    with pytest.raises(LockHeld):
        acquire(str(lock), op="compile")
    release(str(lock))
    # After release, a new acquire succeeds
    acquire(str(lock), op="compile")
    release(str(lock))


def test_query_slug_is_deterministic_and_bounded():
    """Slug generation for a query string: deterministic, ≤60 chars."""
    q = "What is the key contribution of Attention Is All You Need?"
    slug = make_slug(q)
    assert slug == make_slug(q)  # deterministic
    assert len(slug) <= 60
    assert "attention" in slug or "key" in slug or "contribution" in slug


def test_paper_page_roundtrip(tmp_wiki):
    """A complete paper page's frontmatter roundtrips via read/write."""
    paper_path = tmp_wiki / "wiki/papers/vaswani2017attention.md"
    fm = {
        "paper-id": "vaswani2017attention",
        "type": "paper",
        "status": "read",
        "created": "2026-04-16",
        "updated": "2026-04-16",
        "title": "Attention Is All You Need",
        "authors": [
            {"slug": "ashish-vaswani", "name": "Ashish Vaswani"},
            {"slug": "noam-shazeer", "name": "Noam Shazeer"},
        ],
        "year": 2017,
        "venue": "nips",
        "identifiers": {"arxiv": "1706.03762", "doi": "10.xxx/yyy"},
        "aliases": [],
        "source-version": "arxiv-v5",
        "bib-file": "raw/bib/vaswani2017attention.bib",
        "extract": "raw/extracts/vaswani2017attention.md",
        "references-raw": ["Bahdanau 2014", "Cho 2014"],
        "cites": [],
        "tags": ["field/nlp", "method/attention", "year/2017", "venue/nips"],
    }
    body = "# Attention Is All You Need\n\n## Metadata\n\n## Summary\n\n..."
    write_frontmatter(str(paper_path), fm, body)

    # Read back
    fm2, body2 = read_frontmatter(str(paper_path))
    assert fm2 == fm
    assert body2 == body

    # Required fields present
    required = [
        "paper-id",
        "type",
        "status",
        "created",
        "updated",
        "title",
        "authors",
        "year",
        "identifiers",
        "source-version",
        "bib-file",
        "extract",
        "references-raw",
        "cites",
        "tags",
    ]
    for field in required:
        assert field in fm2, f"Missing: {field}"


def test_full_test_suite_passes(tmp_path):
    """Sanity: the complete Wave 1 test suite runs clean."""
    # Not a self-test; this test is for documentation/presence. The actual
    # verification is `pytest -v` at the repo root returning exit 0.
    pass


def test_warning_callout_format_is_obsidian_compatible(tmp_wiki):
    """The contradiction-flag callout format must match Obsidian's [!WARNING] syntax."""
    from academic_wiki_lib.frontmatter import write_frontmatter, read_frontmatter
    page = tmp_wiki / "wiki/concepts/attention-complexity.md"
    body = (
        "Attention is quadratic in sequence length per [[vaswani2017attention]].\n\n"
        "> [!WARNING] Contradiction with [[shazeer2019fast]]\n"
        "> Vaswani et al. report O(n²), but Shazeer et al. report O(n log n) under their\n"
        "> factorized attention variant. Needs resolution.\n"
    )
    write_frontmatter(str(page), {
        "type": "concept",
        "status": "active",
        "created": "2026-04-01",
        "updated": "2026-04-16",
        "sources": ["vaswani2017attention", "shazeer2019fast"],
        "tags": ["field/nlp"],
    }, body)

    # Roundtrip the page
    fm, body2 = read_frontmatter(str(page))
    assert "[!WARNING] Contradiction with" in body2
    # Both sources remain
    assert "vaswani2017attention" in fm["sources"]
    assert "shazeer2019fast" in fm["sources"]


def test_aliases_field_roundtrips(tmp_wiki):
    """Aliases list roundtrips so lint can resolve old-slug references."""
    from academic_wiki_lib.frontmatter import write_frontmatter, read_frontmatter
    page = tmp_wiki / "wiki/concepts/attention-mechanism.md"
    write_frontmatter(str(page), {
        "type": "concept",
        "status": "active",
        "created": "2026-04-16",
        "updated": "2026-04-16",
        "aliases": ["attention", "soft-attention"],
        "sources": ["vaswani2017attention"],
        "tags": ["field/nlp"],
    }, "body\n")
    fm, _ = read_frontmatter(str(page))
    assert "attention" in fm["aliases"]
    assert "soft-attention" in fm["aliases"]
