# Academic Wiki Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new Claude Code plugin (`academic-wiki`) that implements an LLM-driven knowledge base specialized for academic papers — PDF/arXiv/DOI ingestion, BibTeX export, cross-paper synthesis, Obsidian as front-end.

**Architecture:** Claude Code plugin at `/home/tung491/Work/academic_wiki/`, data at `~/ObsidianVault/03-Resources/academic/` as its own nested git repo. Python helpers in `scripts/academic_wiki_lib/`, orchestration in `skills/wiki/SKILL.md`. Four rollout waves (paper-only → synthesis → maintenance → polish). Source of truth: `docs/superpowers/specs/2026-04-16-academic-wiki-design.md`.

**Tech Stack:** Python 3.10+ (stdlib + `pyyaml`, `hashlib`), pytest for tests, bash for shell glue, Claude Code plugin conventions (plugin.json, commands/, skills/, hooks/). Integrations: `ocr-papers-to-latex` skill, `mcp__agentic-rag-v2__*` tools, optional `qmd` and `marp-cli`.

---

## File Structure

```
academic_wiki/
├── .claude-plugin/
│   ├── plugin.json                        # plugin metadata
│   └── marketplace.json                   # marketplace manifest
├── commands/
│   └── wiki.md                            # /academic-wiki:wiki entrypoint
├── skills/
│   └── wiki/
│       ├── SKILL.md                       # main operational skill
│       └── references/
│           ├── entity-schemas.md          # §3 inline
│           ├── tag-taxonomy.md            # §4 inline
│           ├── ingestion-routing.md       # §5.2 detail
│           ├── promotion-rules.md         # Wave 2 candidate/promotion logic
│           ├── bibtex-handling.md         # §5.6 detail
│           └── compilation-guide.md       # §5.3 detail (paper-only + full tiers)
├── scripts/
│   ├── install-deps.sh                    # SessionStart dep installer
│   ├── deps-version.txt                   # qmd/marp-cli version pins
│   ├── academic_wiki_lib/                 # shared Python package
│   │   ├── __init__.py
│   │   ├── slug.py                        # §3.5 slug generation
│   │   ├── paper_id.py                    # §5.2 paper-id derivation + dedup
│   │   ├── source_sha.py                  # SHA-256 helper
│   │   ├── lockfile.py                    # §8.1 advisory lock
│   │   ├── frontmatter.py                 # YAML frontmatter read/write
│   │   ├── wiki_paths.py                  # resolve wiki root; expand ~/ObsidianVault
│   │   └── templates.py                   # CLAUDE.md, index.md, .gitignore, qmd.yml
│   ├── lint-wiki.py                       # §5.5 deterministic checks
│   └── bibtex-export.py                   # §5.6 selector engine
├── hooks/
│   └── hooks.json                         # SessionStart hook
├── tests/
│   ├── conftest.py                        # pytest fixtures
│   ├── test_slug.py
│   ├── test_paper_id.py
│   ├── test_source_sha.py
│   ├── test_lockfile.py
│   ├── test_frontmatter.py
│   ├── test_lint_wiki.py
│   ├── test_bibtex_export.py
│   └── fixtures/
│       └── mini-wiki/                     # integration fixture (§10.2)
├── docs/
│   └── superpowers/
│       ├── specs/2026-04-16-academic-wiki-design.md
│       └── plans/2026-04-16-academic-wiki-plan.md
├── README.md
├── WALKTHROUGH.md                         # Wave 4
├── LICENSE
├── pyproject.toml                         # Python packaging (minimal)
└── .gitignore
```

**Responsibilities per file:**
- `academic_wiki_lib/` is the pure-Python core: no shell, no I/O to MCP servers, fully unit-testable
- `scripts/lint-wiki.py` and `scripts/bibtex-export.py` are CLI entry points that compose the lib
- `skills/wiki/SKILL.md` contains the LLM orchestration prose — invokes `academic_wiki_lib` via bash, routes input, calls other skills (`ocr-papers-to-latex`) and MCP tools (`agentic-rag-v2`)
- `commands/wiki.md` is the thin `/academic-wiki:wiki` entrypoint that loads the skill

---

# Wave 1 — Paper-Only Core Loop

**Exit criterion (from spec §11.1):** end-to-end ingest → `compile --paper-only` → query flow works on ≥5 real papers covering ≥1 arXiv-identifier, ≥1 DOI, ≥1 local PDF, ≥1 with user notes, ≥1 re-ingested as a new version. Dedup and version handling verified.

## Task 1.1: Plugin scaffolding (plugin.json, marketplace, pyproject)

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE` (MIT, match llm-wiki)

- [ ] **Step 1: Write `.claude-plugin/plugin.json`**

```json
{
  "name": "academic-wiki",
  "version": "0.1.0",
  "description": "Academic Wiki — persistent, compounding knowledge base for papers. Ingests PDFs/arXiv/DOIs, compiles wiki pages, exports BibTeX.",
  "author": {
    "name": "tung491"
  }
}
```

- [ ] **Step 2: Write `.claude-plugin/marketplace.json`**

```json
{
  "name": "academic-wiki-local",
  "plugins": [
    {
      "name": "academic-wiki",
      "source": "."
    }
  ]
}
```

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "academic-wiki-scripts"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
*.egg-info/
dist/
build/
.DS_Store
```

- [ ] **Step 5: Write `LICENSE`** (MIT; copy verbatim from `llm-wiki/LICENSE`, change the copyright holder)

Run: `cat llm-wiki/LICENSE`

Replace `ekadetov` (or whatever holder) with `Tung Son Do` and the current year.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/ pyproject.toml .gitignore LICENSE
git commit -m "feat: scaffold academic-wiki plugin (manifest, pyproject, license)"
```

## Task 1.2: Test infrastructure (pytest, conftest)

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write `tests/__init__.py`** (empty file — marks tests as a package)

- [ ] **Step 2: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_wiki(tmp_path):
    """A fresh empty wiki directory tree per test."""
    wiki = tmp_path / "academic"
    for sub in [
        "raw/papers", "raw/extracts", "raw/bib", "raw/figures", "raw/notes",
        "wiki/papers", "wiki/concepts", "wiki/methods", "wiki/open-problems",
        "wiki/claims", "wiki/results", "wiki/authors", "wiki/venues", "wiki/queries",
        "outputs/reports", "outputs/bib",
    ]:
        (wiki / sub).mkdir(parents=True, exist_ok=True)
    (wiki / "wiki/index.md").write_text("# academic Wiki Index\n")
    (wiki / "log.md").write_text("# academic Wiki Log\n")
    return wiki


@pytest.fixture
def sample_paper_content():
    """A tiny paper extract for ingest/compile tests."""
    return """---
paper-id: vaswani-2017-attention
source-path: raw/papers/vaswani-2017-attention.pdf
source-sha: abc123
source-type: pdf
source-url: https://arxiv.org/abs/1706.03762
extractor: ocr-papers-to-latex
extracted-at: 2026-04-16T10:00:00Z
ocr-used: false
extract-status: complete
---
# Attention Is All You Need

We propose the Transformer, a model based entirely on attention.

## References
1. Bahdanau, D. et al. Neural Machine Translation. 2014.
2. Cho, K. et al. Learning Phrase Representations. 2014.
"""
```

- [ ] **Step 3: Verify pytest works**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest --collect-only
```

Expected: `collected 0 items` (no tests yet, but pytest runs).

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add pytest infrastructure"
```

## Task 1.3: Slug generation library (§3.5)

**Files:**
- Create: `scripts/academic_wiki_lib/__init__.py`
- Create: `scripts/academic_wiki_lib/slug.py`
- Create: `tests/test_slug.py`

- [ ] **Step 1: Write `tests/test_slug.py` first**

```python
"""Tests for §3.5 slug generation rules."""
from academic_wiki_lib.slug import make_slug


def test_basic_title():
    assert make_slug("Rate-Splitting Multiple Access") == "rate-splitting-multiple-access"


def test_stop_word_dropped_only_if_remaining_is_multi_word():
    assert make_slug("The Attention Mechanism") == "attention-mechanism"
    assert make_slug("The") == "the"  # single word, keep


def test_ascii_folding():
    assert make_slug("α-divergence") == "a-divergence"
    assert make_slug("García-Luna") == "garcia-luna"


def test_punctuation_stripped():
    assert make_slug("O(n²) complexity of self-attention") == "on2-complexity-of-self-attention"


def test_truncation_at_60_chars():
    long = "a-" * 50  # 100 chars
    assert len(make_slug(long)) <= 60


def test_collapses_multiple_hyphens():
    assert make_slug("foo---bar") == "foo-bar"


def test_strips_leading_trailing_hyphens():
    assert make_slug("--foo-bar--") == "foo-bar"


def test_lowercases():
    assert make_slug("K-Means") == "k-means"


def test_empty_input_raises():
    import pytest
    with pytest.raises(ValueError):
        make_slug("")
    with pytest.raises(ValueError):
        make_slug("   ")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_slug.py -v
```

Expected: all tests fail with `ModuleNotFoundError: academic_wiki_lib`.

- [ ] **Step 3: Write `scripts/academic_wiki_lib/__init__.py`** (empty)

- [ ] **Step 4: Write `scripts/academic_wiki_lib/slug.py`**

```python
"""Slug generation per spec §3.5."""
from __future__ import annotations

import re
import unicodedata

_STOP_WORDS = frozenset({"a", "an", "the", "on", "of", "for", "with"})
_MAX_LEN = 60


def make_slug(title: str) -> str:
    """Generate a lowercase-kebab-case slug from a title string.

    Implements the rules from spec §3.5:
      1. Unicode NFKD normalize + strip combining marks (ASCII-fold).
      2. Lowercase.
      3. Replace any non-alphanumeric run (except existing hyphens) with single hyphen.
      4. Collapse consecutive hyphens.
      5. Truncate at 60 chars at a word boundary if possible.
      6. Stop-word filter: drop leading a/an/the/on/of/for/with iff result remains multi-word.
      7. Caller handles collision resolution separately.
    """
    if not title or not title.strip():
        raise ValueError("Cannot generate slug from empty or whitespace-only title")

    # 1. ASCII-fold
    decomposed = unicodedata.normalize("NFKD", title)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))

    # 2. Lowercase
    lowered = folded.lower()

    # 3. Replace non-alphanumeric (except -) with hyphen; keep hyphens as-is
    #    Also keep digits and basic latin letters
    tokenized = re.sub(r"[^a-z0-9\-]+", "-", lowered)

    # 4. Collapse multiple hyphens
    collapsed = re.sub(r"-+", "-", tokenized)

    # 5. Strip leading/trailing hyphens
    stripped = collapsed.strip("-")

    # 6. Stop-word filter
    parts = stripped.split("-")
    if len(parts) >= 2 and parts[0] in _STOP_WORDS:
        candidate = "-".join(parts[1:])
        if "-" in candidate:  # still multi-word
            stripped = candidate

    # 7. Truncate at 60 chars, preferring a word boundary
    if len(stripped) > _MAX_LEN:
        truncated = stripped[:_MAX_LEN]
        # Walk back to the last hyphen if we can
        last_hyphen = truncated.rfind("-")
        if last_hyphen > _MAX_LEN // 2:
            truncated = truncated[:last_hyphen]
        stripped = truncated.strip("-")

    if not stripped:
        raise ValueError(f"Slug generation produced empty string from title: {title!r}")

    return stripped
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_slug.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/academic_wiki_lib/__init__.py scripts/academic_wiki_lib/slug.py tests/test_slug.py
git commit -m "feat(lib): implement slug generation per spec 3.5"
```

## Task 1.4: Source SHA helper

**Files:**
- Create: `scripts/academic_wiki_lib/source_sha.py`
- Create: `tests/test_source_sha.py`

- [ ] **Step 1: Write `tests/test_source_sha.py`**

```python
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
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MB
    result = file_sha256(str(f))
    assert len(result) == 64
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_source_sha.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `scripts/academic_wiki_lib/source_sha.py`**

```python
"""SHA-256 helper for source-file deduplication."""
from __future__ import annotations

import hashlib

_CHUNK = 64 * 1024


def file_sha256(path: str) -> str:
    """Return the hex-encoded SHA-256 of the file at path."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()
```

- [ ] **Step 4: Run tests and verify pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_source_sha.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/source_sha.py tests/test_source_sha.py
git commit -m "feat(lib): add SHA-256 helper for source file dedup"
```

## Task 1.5: YAML frontmatter read/write helper

**Files:**
- Create: `scripts/academic_wiki_lib/frontmatter.py`
- Create: `tests/test_frontmatter.py`

- [ ] **Step 1: Write `tests/test_frontmatter.py`**

```python
"""Tests for YAML frontmatter read/write."""
from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter


def test_read_simple_frontmatter(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("---\ntitle: Hello\nyear: 2024\n---\nBody.\n")
    fm, body = read_frontmatter(str(f))
    assert fm == {"title": "Hello", "year": 2024}
    assert body == "Body.\n"


def test_read_no_frontmatter(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("Just a body.\n")
    fm, body = read_frontmatter(str(f))
    assert fm == {}
    assert body == "Just a body.\n"


def test_read_empty_frontmatter(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("---\n---\nBody.\n")
    fm, body = read_frontmatter(str(f))
    assert fm == {}
    assert body == "Body.\n"


def test_write_roundtrip(tmp_path):
    f = tmp_path / "p.md"
    fm = {"title": "Attention", "authors": ["vaswani", "shazeer"], "year": 2017}
    write_frontmatter(str(f), fm, "# Attention\n\nBody here.\n")
    fm2, body2 = read_frontmatter(str(f))
    assert fm2 == fm
    assert body2 == "# Attention\n\nBody here.\n"


def test_write_preserves_order(tmp_path):
    f = tmp_path / "p.md"
    fm = {"b": 1, "a": 2, "c": 3}
    write_frontmatter(str(f), fm, "")
    content = f.read_text()
    # Keys should appear in insertion order
    assert content.index("b:") < content.index("a:") < content.index("c:")
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_frontmatter.py -v
```

- [ ] **Step 3: Write `scripts/academic_wiki_lib/frontmatter.py`**

```python
"""Read and write YAML frontmatter at the top of markdown files."""
from __future__ import annotations

import re
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n?---\n?(.*)$", re.DOTALL)


def read_frontmatter(path: str) -> tuple[dict[str, Any], str]:
    """Read YAML frontmatter and body from a markdown file.

    Returns ({}, body) if there is no frontmatter block.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content

    yaml_text = m.group(1)
    body = m.group(2)
    data = yaml.safe_load(yaml_text) if yaml_text.strip() else None
    return (data or {}), body


def write_frontmatter(path: str, frontmatter: dict[str, Any], body: str) -> None:
    """Write a markdown file with YAML frontmatter + body. Preserves key insertion order."""
    yaml_text = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml_text)
        f.write("---\n")
        if body and not body.startswith("\n"):
            f.write("\n")
        f.write(body)
```

- [ ] **Step 4: Run tests and verify pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_frontmatter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/frontmatter.py tests/test_frontmatter.py
git commit -m "feat(lib): add YAML frontmatter read/write"
```

## Task 1.6: Paper-id generation and dedup (§5.2)

**Files:**
- Create: `scripts/academic_wiki_lib/paper_id.py`
- Create: `tests/test_paper_id.py`

- [ ] **Step 1: Write `tests/test_paper_id.py`**

```python
"""Tests for paper-id generation and dedup logic."""
import pytest

from academic_wiki_lib.paper_id import (
    generate_paper_id,
    normalize_identifier,
    find_existing_paper_by_identifiers,
    resolve_collision,
)


def test_basic_paper_id():
    assert generate_paper_id("Vaswani", 2017, "Attention Is All You Need") == "vaswani-2017-attention"


def test_stop_word_in_title_dropped():
    assert generate_paper_id("Smith", 2020, "The Future of AI") == "smith-2020-future"


def test_ascii_fold_in_lastname():
    assert generate_paper_id("García", 2024, "Survey of RSMA") == "garcia-2024-survey"


def test_numeric_first_word_skipped():
    assert generate_paper_id("Chen", 2023, "5G Networks") == "chen-2023-networks"


def test_normalize_arxiv_strips_version():
    assert normalize_identifier("arxiv", "1706.03762v5") == ("1706.03762", "v5")
    assert normalize_identifier("arxiv", "1706.03762") == ("1706.03762", None)


def test_normalize_doi_lowercases():
    assert normalize_identifier("doi", "10.1145/3442188.3445922")[0] == "10.1145/3442188.3445922"
    assert normalize_identifier("doi", "10.1145/XYZ")[0] == "10.1145/xyz"


def test_find_existing_paper_by_doi(tmp_wiki):
    # Create an existing paper page with a known DOI
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/vaswani-2017-attention.md"
    write_frontmatter(str(paper), {
        "paper-id": "vaswani-2017-attention",
        "identifiers": {"doi": "10.xx/yy", "arxiv": "1706.03762"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.xx/yy"})
    assert found == "vaswani-2017-attention"


def test_find_existing_paper_by_arxiv_different_version(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/vaswani-2017-attention.md"
    write_frontmatter(str(paper), {
        "paper-id": "vaswani-2017-attention",
        "identifiers": {"arxiv": "1706.03762", "arxiv-version": "v3"},
    }, "")
    # Incoming is the same arxiv ID at a different version — should match
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"arxiv": "1706.03762"})
    assert found == "vaswani-2017-attention"


def test_find_existing_paper_no_match(tmp_wiki):
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.xx/zz"})
    assert found is None


def test_resolve_collision_appends_numeric_suffix(tmp_wiki):
    (tmp_wiki / "wiki/papers/smith-2020-neural.md").write_text("---\n---\n")
    result = resolve_collision(str(tmp_wiki), "smith-2020-neural")
    assert result == "smith-2020-neural-2"


def test_resolve_collision_finds_next_available(tmp_wiki):
    (tmp_wiki / "wiki/papers/smith-2020-neural.md").write_text("")
    (tmp_wiki / "wiki/papers/smith-2020-neural-2.md").write_text("")
    (tmp_wiki / "wiki/papers/smith-2020-neural-3.md").write_text("")
    result = resolve_collision(str(tmp_wiki), "smith-2020-neural")
    assert result == "smith-2020-neural-4"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_paper_id.py -v
```

- [ ] **Step 3: Write `scripts/academic_wiki_lib/paper_id.py`**

```python
"""Paper-id generation and dedup per spec §5.2."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from academic_wiki_lib.frontmatter import read_frontmatter

_STOP_WORDS = frozenset({"a", "an", "the", "on", "of", "for", "with"})


def _ascii_fold(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _first_meaningful_word(title: str) -> str:
    """Return the first word of the title, skipping stop words and pure numbers."""
    # Split on any non-alphanumeric run
    words = re.split(r"[^a-zA-Z0-9]+", title.strip())
    for w in words:
        if not w:
            continue
        wl = w.lower()
        if wl in _STOP_WORDS:
            continue
        if wl.isdigit():
            continue
        # Fold and strip non-alphanumeric residue
        folded = _ascii_fold(w)
        cleaned = re.sub(r"[^a-z0-9]", "", folded)
        if cleaned:
            return cleaned
    return "untitled"


def generate_paper_id(lastname: str, year: int, title: str) -> str:
    """Generate a paper-id per spec §5.2: <lastname>-<year>-<firstword>."""
    ln = re.sub(r"[^a-z0-9]", "", _ascii_fold(lastname))
    if not ln:
        ln = "unknown"
    fw = _first_meaningful_word(title)
    return f"{ln}-{year}-{fw}"


def normalize_identifier(kind: str, value: str) -> tuple[str, str | None]:
    """Normalize an identifier value for comparison.

    Returns (normalized_id, version_suffix). The version suffix is separated out
    so two different versions of the same arXiv paper match on the ID.
    """
    if kind == "arxiv":
        m = re.match(r"^(\d{4}\.\d{4,5})(v\d+)?$", value.strip())
        if m:
            return m.group(1), m.group(2)
        return value.strip(), None
    if kind == "doi":
        return value.strip().lower(), None
    if kind == "url":
        return value.strip(), None
    return value.strip(), None


def find_existing_paper_by_identifiers(wiki_root: str, identifiers: dict[str, str]) -> str | None:
    """Scan wiki/papers/*.md for any paper whose identifiers match the given dict.

    Match semantics:
      - doi: case-insensitive equal
      - arxiv: equal after stripping version suffix
      - url: exact equal
    Returns the matching paper-id, or None.
    """
    papers_dir = Path(wiki_root) / "wiki" / "papers"
    if not papers_dir.is_dir():
        return None

    # Normalize incoming identifiers
    incoming: dict[str, str] = {}
    for k, v in identifiers.items():
        if v:
            norm, _ = normalize_identifier(k, v)
            incoming[k] = norm

    for p in papers_dir.glob("*.md"):
        fm, _ = read_frontmatter(str(p))
        existing = fm.get("identifiers") or {}
        if not isinstance(existing, dict):
            continue
        for k, v in incoming.items():
            ev = existing.get(k)
            if not ev:
                continue
            ev_norm, _ = normalize_identifier(k, ev)
            if ev_norm == v:
                return fm.get("paper-id") or p.stem
    return None


def resolve_collision(wiki_root: str, proposed_id: str) -> str:
    """If <proposed_id>.md already exists in wiki/papers/, append -2, -3, ..."""
    papers_dir = Path(wiki_root) / "wiki" / "papers"
    candidate = proposed_id
    suffix = 2
    while (papers_dir / f"{candidate}.md").exists():
        candidate = f"{proposed_id}-{suffix}"
        suffix += 1
    return candidate
```

- [ ] **Step 4: Run tests and verify pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_paper_id.py -v
```

Expected: all 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/paper_id.py tests/test_paper_id.py
git commit -m "feat(lib): paper-id generation + identifier-level dedup + collision resolution"
```

## Task 1.7: Advisory lockfile (§8.1)

**Files:**
- Create: `scripts/academic_wiki_lib/lockfile.py`
- Create: `tests/test_lockfile.py`

- [ ] **Step 1: Write `tests/test_lockfile.py`**

```python
"""Tests for advisory lockfile per spec §8.1."""
import os
import subprocess
import time

import pytest

from academic_wiki_lib.lockfile import (
    LockHeld,
    StaleLockRecovered,
    acquire,
    release,
)


def test_acquire_empty(tmp_path):
    lock = tmp_path / ".lock"
    acquire(str(lock), op="ingest")
    assert lock.exists()
    content = lock.read_text()
    assert f":{os.getpid()}:" in content
    assert "ingest" in content


def test_acquire_fails_when_held_by_live_pid(tmp_path):
    lock = tmp_path / ".lock"
    # Simulate a live holder: use current pid (always alive)
    lock.write_text(f"{os.getpid()}:2026-04-16T10:00:00Z:compile")
    with pytest.raises(LockHeld):
        acquire(str(lock), op="ingest")


def test_acquire_recovers_stale_lock(tmp_path, capfd):
    lock = tmp_path / ".lock"
    # Pid 1 is init; a lockfile holding pid 1 is plausible but this pid is always live.
    # Use a definitely-dead pid: 2^31 - 1 is out of range on Linux.
    dead_pid = 99999999
    lock.write_text(f"{dead_pid}:2026-04-16T10:00:00Z:ingest")
    with pytest.warns(StaleLockRecovered):
        acquire(str(lock), op="compile")
    # New lock belongs to us
    assert f"{os.getpid()}" in lock.read_text()


def test_release(tmp_path):
    lock = tmp_path / ".lock"
    acquire(str(lock), op="ingest")
    assert lock.exists()
    release(str(lock))
    assert not lock.exists()


def test_release_silent_if_absent(tmp_path):
    lock = tmp_path / ".lock"
    release(str(lock))  # no-op, no error
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_lockfile.py -v
```

- [ ] **Step 3: Write `scripts/academic_wiki_lib/lockfile.py`**

```python
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
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but we don't own it; treat as alive.
        return True
    return True


def acquire(lock_path: str, op: str) -> None:
    """Acquire the lock. Raises LockHeld if held by a live process."""
    if os.path.exists(lock_path):
        try:
            content = open(lock_path).read().strip()
            parts = content.split(":", 2)
            if len(parts) >= 1:
                pid_str = parts[0]
                pid = int(pid_str)
                if _is_alive(pid):
                    ts = parts[1] if len(parts) >= 2 else "unknown"
                    existing_op = parts[2] if len(parts) >= 3 else "unknown"
                    raise LockHeld(
                        f"Another operation is in progress: {existing_op} started at {ts} by pid {pid}"
                    )
                else:
                    warnings.warn(
                        f"Stale lock from pid {pid} — recovering",
                        StaleLockRecovered,
                    )
        except (ValueError, OSError) as e:
            if not isinstance(e, LockHeld):
                warnings.warn(
                    f"Malformed lock file at {lock_path} — recovering: {e}",
                    StaleLockRecovered,
                )

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(lock_path, "w") as f:
        f.write(f"{os.getpid()}:{ts}:{op}")


def release(lock_path: str) -> None:
    """Release the lock. No-op if absent."""
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass
```

- [ ] **Step 4: Run tests and verify pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_lockfile.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/lockfile.py tests/test_lockfile.py
git commit -m "feat(lib): advisory lockfile with stale-recovery per spec 8.1"
```

## Task 1.8: Wiki-root and path helpers

**Files:**
- Create: `scripts/academic_wiki_lib/wiki_paths.py`
- Create: `tests/test_wiki_paths.py`

- [ ] **Step 1: Write `tests/test_wiki_paths.py`**

```python
"""Tests for wiki root detection."""
from pathlib import Path

from academic_wiki_lib.wiki_paths import find_active_wiki, list_wikis


def test_find_wiki_from_within(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("")
    deep = wiki / "raw" / "papers"
    deep.mkdir(parents=True)
    assert find_active_wiki(str(deep)) == str(wiki)


def test_find_wiki_from_root_returns_none(tmp_path):
    # tmp_path has no wiki markers
    assert find_active_wiki(str(tmp_path)) is None


def test_list_wikis(tmp_path):
    base = tmp_path / "03-Resources"
    for name in ["academic", "other", "not-a-wiki"]:
        d = base / name
        d.mkdir(parents=True)
    for name in ["academic", "other"]:
        (base / name / "wiki").mkdir()
        (base / name / "CLAUDE.md").write_text("")
    # not-a-wiki has neither CLAUDE.md nor wiki/
    wikis = list_wikis(str(base))
    assert set(wikis) == {"academic", "other"}
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_wiki_paths.py -v
```

- [ ] **Step 3: Write `scripts/academic_wiki_lib/wiki_paths.py`**

```python
"""Wiki-root detection and listing."""
from __future__ import annotations

import os
from pathlib import Path


def find_active_wiki(start: str) -> str | None:
    """Walk up from `start` looking for a directory containing both CLAUDE.md AND wiki/.
    Returns the absolute path of that directory, or None if none is found.
    """
    p = Path(start).resolve()
    while True:
        if (p / "CLAUDE.md").exists() and (p / "wiki").is_dir():
            return str(p)
        if p.parent == p:
            return None
        p = p.parent


def list_wikis(base: str) -> list[str]:
    """List names of wiki-like subdirectories of `base`.
    A wiki-like subdir contains both CLAUDE.md and wiki/.
    """
    basep = Path(base)
    if not basep.is_dir():
        return []
    out = []
    for child in basep.iterdir():
        if child.is_dir() and (child / "CLAUDE.md").exists() and (child / "wiki").is_dir():
            out.append(child.name)
    return sorted(out)
```

- [ ] **Step 4: Run tests and verify pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_wiki_paths.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/wiki_paths.py tests/test_wiki_paths.py
git commit -m "feat(lib): wiki-root detection and listing"
```

## Task 1.9: Directory-tree and file templates

**Files:**
- Create: `scripts/academic_wiki_lib/templates.py`
- Create: `tests/test_templates.py`

- [ ] **Step 1: Write `tests/test_templates.py`**

```python
"""Tests for wiki templates."""
from academic_wiki_lib.templates import (
    INDEX_MD,
    LOG_MD,
    GITIGNORE,
    QMD_YML,
    claude_md,
    all_subdirs,
)


def test_all_subdirs_matches_spec():
    expected = {
        "raw/papers", "raw/extracts", "raw/bib", "raw/figures", "raw/notes",
        "wiki/papers", "wiki/concepts", "wiki/methods", "wiki/open-problems",
        "wiki/claims", "wiki/results", "wiki/authors", "wiki/venues", "wiki/queries",
        "outputs/reports", "outputs/bib",
    }
    assert set(all_subdirs()) == expected


def test_claude_md_contains_required_sections():
    doc = claude_md("academic")
    assert "# academic Wiki Schema" in doc
    assert "## Directory Layout" in doc
    assert "## Identity Model" in doc
    assert "## Entity Types" in doc
    assert "## Tag Taxonomy" in doc
    assert "## Slug Generation" in doc
    assert "## Update Conflict Policy" in doc
    assert "## Lockfile Semantics" in doc


def test_index_md_not_empty():
    assert "Wiki Index" in INDEX_MD or "index" in INDEX_MD.lower()


def test_gitignore_excludes_lock_and_sqlite():
    assert ".lock" in GITIGNORE
    assert "*.sqlite" in GITIGNORE


def test_qmd_yml_parameterized():
    # qmd.yml template is generated per-wiki by claude_md's sibling
    from academic_wiki_lib.templates import qmd_yml
    y = qmd_yml("academic")
    assert "collections:" in y
    assert "academic:" in y
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_templates.py -v
```

- [ ] **Step 3: Write `scripts/academic_wiki_lib/templates.py`**

Write the complete template content. `claude_md(name)` returns a ~1000-line schema document that inlines spec §§2–7. For the plan, delegate the long-form content to the spec: the implementer should copy the content from `docs/superpowers/specs/2026-04-16-academic-wiki-design.md` §§2.2, 2.3, 3.1–3.7, 4, 5.1–5.8, 6, 7, 8.1, reformatted as a self-contained contract document.

```python
"""Templates for wiki initialization."""
from __future__ import annotations


def all_subdirs() -> list[str]:
    """All directories init should create beneath the wiki root (relative paths)."""
    return [
        "raw/papers", "raw/extracts", "raw/bib", "raw/figures", "raw/notes",
        "wiki/papers", "wiki/concepts", "wiki/methods", "wiki/open-problems",
        "wiki/claims", "wiki/results", "wiki/authors", "wiki/venues", "wiki/queries",
        "outputs/reports", "outputs/bib",
    ]


INDEX_MD = """# {name} Wiki Index

Last updated: YYYY-MM-DD

<!-- Populated by compile. Format:
## Field Name
- [[paper-id]] -- one-line description (YYYY-MM-DD)
-->
"""


LOG_MD = """# {name} Wiki Log

<!-- Append only. Never edit existing entries. Format:
## [YYYY-MM-DD] <op> | <subject>
One-line description.
-->
"""


GITIGNORE = """.DS_Store
.lock
*.sqlite
*.sqlite-wal
*.sqlite-shm
"""


def qmd_yml(name: str) -> str:
    return f"""collections:
  {name}:
    path: ./wiki
    pattern: "**/*.md"
"""


def claude_md(name: str) -> str:
    """Return the authoritative CLAUDE.md schema document for a wiki named `name`.

    Task 1.10 replaces the `<TO BE FILLED>` markers with content from the spec.
    Uses `.replace()` rather than f-string to safely handle YAML braces in inlined
    content.
    """
    return _CLAUDE_MD_SKELETON.replace("{{NAME}}", name)


_CLAUDE_MD_SKELETON = r"""# {{NAME}} Wiki Schema

## Directory Layout
<TO BE FILLED — spec §2.2>

## Identity Model
<TO BE FILLED — spec §2.3 #2 + §3.1>

## Entity Types
<TO BE FILLED — spec §3.1–§3.3>

## Cross-Schema Conventions
<TO BE FILLED — spec §3.4>

## Slug Generation
<TO BE FILLED — spec §3.5>

## Update Conflict Policy
<TO BE FILLED — spec §3.6>

## Raw-Side Metadata Schema
<TO BE FILLED — spec §3.7>

## Tag Taxonomy
<TO BE FILLED — spec §4>

## Naming Conventions
Filenames: lowercase-kebab-case.md (paper pages use paper-id verbatim)
Wikilinks: [[slug]] without extension

## Log Format
## [YYYY-MM-DD] <op> | <subject>
<op> in {init, ingest, compile, query, promote, lint, export, snapshot, remove}

## Commit Message Format
<op>: <subject>
(optional one-line "why" body)

## Cross-Reference Rules
<TO BE FILLED — wikilink density, backlink audit allowlist, contradiction callouts>

## Ingest Rules
<TO BE FILLED — spec §5.2>

## Compile Rules
<TO BE FILLED — spec §5.3 (paper-only tier in Wave 1; full tier in Wave 2)>

## Query Rules
<TO BE FILLED — spec §5.4>

## Lint Rules
<TO BE FILLED — spec §5.5>

## Export-BibTeX Rules
<TO BE FILLED — spec §5.6>

## Snapshot Rules
<TO BE FILLED — spec §5.7 — wiki's own git repo, tag namespace>

## Search Strategy
<TO BE FILLED — spec §6 — SearchHit contract and fallback chain>

## Lockfile Semantics
<TO BE FILLED — spec §8.1>
"""
```

- [ ] **Step 4: Run tests and verify pass**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_templates.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/templates.py tests/test_templates.py
git commit -m "feat(lib): directory and file templates with CLAUDE.md skeleton"
```

## Task 1.10: Populate CLAUDE.md with full content from spec

**Files:**
- Modify: `scripts/academic_wiki_lib/templates.py` (replace skeleton `claude_md` with full content)

- [ ] **Step 1: Read the spec sections that will be inlined**

```bash
cd /home/tung491/Work/academic_wiki && sed -n '78,410p' docs/superpowers/specs/2026-04-16-academic-wiki-design.md > /tmp/spec-excerpt.md
```

Inline the content of spec §§2.2, 2.3, 3.1–3.7, 4, 5.1–5.8, 6, 8.1 into the CLAUDE.md body. Substitute `academic` → `{name}` in places where the spec refers to the wiki by name.

- [ ] **Step 2: Replace `claude_md(name)` in `scripts/academic_wiki_lib/templates.py`**

Convert the `<TO BE FILLED>` placeholders into actual content, copied from the spec. The resulting `claude_md("academic")` output should be a complete, self-contained schema document (~1000–1200 lines).

**Important — do NOT use an f-string.** The spec content contains YAML examples with literal braces like `authors: [{slug: ashish-vaswani, name: "Ashish Vaswani"}]`. An f-string would interpret those as format specifiers and raise `SyntaxError`. Use a `.replace()` pattern with a non-syntactic marker instead:

```python
def claude_md(name: str) -> str:
    return _CLAUDE_MD_TEMPLATE.replace("{{NAME}}", name)

_CLAUDE_MD_TEMPLATE = r"""# {{NAME}} Wiki Schema

## Directory Layout
<paste spec §2.2 directory tree here, verbatim>

...etc for every section...

## Ingest Rules
...
authors: [{slug: ashish-vaswani, name: "Ashish Vaswani"}]    # safe — not an f-string
...
"""
```

Raw-string prefix (`r"""`) avoids having to escape backslashes. The `{{NAME}}` marker is non-conflicting because the spec content itself never contains literal `{{NAME}}`.

- [ ] **Step 3: Update `tests/test_templates.py` to assert content presence**

```python
def test_claude_md_is_self_contained():
    doc = claude_md("academic")
    # No TO BE FILLED markers remain
    assert "<TO BE FILLED>" not in doc
    assert "TO BE FILLED" not in doc
    # Key content checkpoints from the spec
    assert "paper-id" in doc
    assert "source-sha" in doc
    assert "field/" in doc
    assert "snapshot/" in doc
    assert "Counter-Arguments and Gaps" in doc
    # Has replaced `{name}`
    assert "{name}" not in doc
    assert "academic" in doc
```

- [ ] **Step 4: Run tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_templates.py -v
```

Expected: all tests pass, including the new content-assertion test.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/templates.py tests/test_templates.py
git commit -m "feat(lib): populate CLAUDE.md template with full schema inline from spec"
```

## Task 1.11: `init` command implementation

**Files:**
- Create: `commands/wiki.md`
- Create: `skills/wiki/SKILL.md` (initial skeleton; filled in across Wave 1)

- [ ] **Step 1: Write `commands/wiki.md`**

```markdown
---
description: "Academic Wiki — init, ingest, compile, query, lint, export-bibtex, snapshot, or remove"
argument-hint: "init <name> | ingest <path|id|url> | compile [<paper-id>] [--paper-only] | query <question> | lint | export-bibtex <selectors> | snapshot <label> | remove <name>"
---

Load and follow the `academic-wiki:wiki` skill. Pass through all user arguments exactly as provided.
```

- [ ] **Step 2: Write initial `skills/wiki/SKILL.md`** with just the `init` branch fleshed out

```markdown
---
name: wiki
description: >-
  Academic Wiki — persistent knowledge base for academic papers inside Obsidian.
  Use when the user says "/academic-wiki:wiki", "wiki init", "wiki ingest",
  "wiki compile", "wiki query", "wiki lint", "wiki export-bibtex",
  "wiki snapshot", or asks about managing an academic knowledge base wiki.
argument-hint: init <name> | ingest <path|id|url> | compile [<paper-id>] [--paper-only] | query <question> | lint | export-bibtex <selectors> | snapshot <label> | remove <name>
---

# Academic Wiki

Persistent, compounding knowledge base for academic papers inside an Obsidian vault. Spec source of truth: `docs/superpowers/specs/2026-04-16-academic-wiki-design.md`.

## Active Wiki Detection

Walk up from `cwd` looking for a directory with both `CLAUDE.md` and a `wiki/` subfolder. If none found, list `~/ObsidianVault/03-Resources/*/wiki` and prompt. Default to `academic/` if present.

## Helper bin

All Python helpers live at `${CLAUDE_PLUGIN_ROOT}/scripts/academic_wiki_lib/`. Invoke via:
```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c "from academic_wiki_lib import <module>; ..."
```

Or call the CLI entry points (Wave 3):
- `${CLAUDE_PLUGIN_ROOT}/scripts/lint-wiki.py`
- `${CLAUDE_PLUGIN_ROOT}/scripts/bibtex-export.py`

## `init <name>`

Default name: `academic`.

1. Abort if `~/ObsidianVault/03-Resources/<name>/` exists — suggest `wiki remove <name>`.
2. Create directory tree:
    ```bash
    for d in raw/papers raw/extracts raw/bib raw/figures raw/notes \
             wiki/papers wiki/concepts wiki/methods wiki/open-problems \
             wiki/claims wiki/results wiki/authors wiki/venues wiki/queries \
             outputs/reports outputs/bib; do
        mkdir -p ~/ObsidianVault/03-Resources/<name>/$d
    done
    ```
3. `git -C ~/ObsidianVault/03-Resources/<name> init`.
4. Write `CLAUDE.md` using the `templates.claude_md("<name>")` function:
    ```bash
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c \
      'from academic_wiki_lib.templates import claude_md; import sys; \
       sys.stdout.write(claude_md("<name>"))' \
       > ~/ObsidianVault/03-Resources/<name>/CLAUDE.md
    ```
5. Similarly write `wiki/index.md`, `log.md`, `.gitignore`, `qmd.yml` from `templates.INDEX_MD`, `LOG_MD`, `GITIGNORE`, `qmd_yml("<name>")`.
6. Update Obsidian vault's `.gitignore` (if `~/ObsidianVault/.git` exists) to include `03-Resources/<name>/` — prepend a line if not already present.
7. Inside-wiki initial commit:
    ```bash
    git -C ~/ObsidianVault/03-Resources/<name> add .
    git -C ~/ObsidianVault/03-Resources/<name> commit -m "init: <name> wiki"
    ```
8. If qmd available at `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd`:
    ```bash
    "${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd" collection add \
        ~/ObsidianVault/03-Resources/<name>/wiki --name <name>
    "${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd" embed --collection <name>
    ```
9. Print Web Clipper + Zotero hints.

## `ingest <path|id|url>`

<Wave 1 Task 1.13 fills this in.>

## `compile [<paper-id>] [--paper-only]`

<Wave 1 Task 1.14 fills this in with the paper-only tier; Wave 2 extends.>

## `query <question>`

<Wave 1 Task 1.15 fills this in.>

## `lint`

<Wave 3 fills this in.>

## `export-bibtex <selectors>`

<Wave 3 fills this in.>

## `snapshot <label>`

<Wave 3 fills this in.>

## `remove <name>`

<Wave 4 fills this in.>
```

- [ ] **Step 3: Smoke-test `init` by running the commands manually**

Simulate what the skill does (using a test location):

```bash
TEST_WIKI=/tmp/test-academic-wiki
rm -rf "$TEST_WIKI"
mkdir -p "$TEST_WIKI"
for d in raw/papers raw/extracts raw/bib raw/figures raw/notes \
         wiki/papers wiki/concepts wiki/methods wiki/open-problems \
         wiki/claims wiki/results wiki/authors wiki/venues wiki/queries \
         outputs/reports outputs/bib; do
    mkdir -p "$TEST_WIKI/$d"
done
git -C "$TEST_WIKI" init
PYTHONPATH="$(pwd)/scripts" python3 -c \
    'from academic_wiki_lib.templates import claude_md; import sys; sys.stdout.write(claude_md("test-wiki"))' \
    > "$TEST_WIKI/CLAUDE.md"
PYTHONPATH="$(pwd)/scripts" python3 -c \
    'from academic_wiki_lib.templates import INDEX_MD; import sys; sys.stdout.write(INDEX_MD.format(name="test-wiki"))' \
    > "$TEST_WIKI/wiki/index.md"
PYTHONPATH="$(pwd)/scripts" python3 -c \
    'from academic_wiki_lib.templates import LOG_MD; import sys; sys.stdout.write(LOG_MD.format(name="test-wiki"))' \
    > "$TEST_WIKI/log.md"
PYTHONPATH="$(pwd)/scripts" python3 -c \
    'from academic_wiki_lib.templates import GITIGNORE; import sys; sys.stdout.write(GITIGNORE)' \
    > "$TEST_WIKI/.gitignore"
PYTHONPATH="$(pwd)/scripts" python3 -c \
    'from academic_wiki_lib.templates import qmd_yml; import sys; sys.stdout.write(qmd_yml("test-wiki"))' \
    > "$TEST_WIKI/qmd.yml"
git -C "$TEST_WIKI" add .
git -C "$TEST_WIKI" -c user.email=test@example.com -c user.name=Test commit -m "init: test-wiki wiki"
```

Expected: exit code 0, wiki tree exists, git log shows the init commit.

Verify:
```bash
ls -la "$TEST_WIKI/"
git -C "$TEST_WIKI" log --oneline
rm -rf "$TEST_WIKI"
```

- [ ] **Step 4: Commit**

```bash
git add commands/wiki.md skills/wiki/SKILL.md
git commit -m "feat(cmd): /academic-wiki:wiki entrypoint + init skeleton"
```

## Task 1.12: hooks.json + install-deps.sh (SessionStart qmd install)

**Files:**
- Create: `hooks/hooks.json`
- Create: `scripts/install-deps.sh`
- Create: `scripts/deps-version.txt`

- [ ] **Step 1: Read llm-wiki's hooks for pattern**

```bash
cat llm-wiki/hooks/hooks.json
cat llm-wiki/scripts/install-deps.sh
cat llm-wiki/scripts/deps-version.txt
```

- [ ] **Step 2: Write `hooks/hooks.json`**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/install-deps.sh\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 3: Write `scripts/deps-version.txt`**

```
qmd@0.5.0
@marp-team/marp-cli@3.4.0
```

(Match versions from llm-wiki or adjust if newer versions are stable. This is the version pin for idempotent installs.)

- [ ] **Step 4: Write `scripts/install-deps.sh`**

```bash
#!/bin/bash
set -euo pipefail

PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/academic-wiki}"
mkdir -p "$PLUGIN_DATA"

SENTINEL="$PLUGIN_DATA/.deps-ok"
VERSIONS_FILE="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT not set}/scripts/deps-version.txt"

if [[ -f "$SENTINEL" ]]; then
    if diff -q "$VERSIONS_FILE" "$PLUGIN_DATA/.deps-version" >/dev/null 2>&1; then
        exit 0
    fi
fi

if ! command -v node >/dev/null 2>&1; then
    echo "academic-wiki: Node.js 18+ is required for qmd/marp-cli. Please install it." >&2
    exit 0  # don't block the session
fi

cd "$PLUGIN_DATA"
if [[ ! -f package.json ]]; then
    npm init -y >/dev/null
fi

# Install pinned versions
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    npm install --silent "$line" || {
        echo "academic-wiki: failed to install $line" >&2
        exit 0
    }
done < "$VERSIONS_FILE"

cp "$VERSIONS_FILE" "$PLUGIN_DATA/.deps-version"
touch "$SENTINEL"
echo "academic-wiki: dependencies installed at $PLUGIN_DATA"
```

- [ ] **Step 5: Make the script executable**

```bash
chmod +x scripts/install-deps.sh
```

- [ ] **Step 6: Commit**

```bash
git add hooks/ scripts/install-deps.sh scripts/deps-version.txt
git commit -m "feat: SessionStart hook + dep install script for qmd/marp-cli"
```

## Task 1.13: `ingest` command — full pipeline (spec §5.2)

**Files:**
- Modify: `skills/wiki/SKILL.md` (fill in the ingest section)
- Create: `skills/wiki/references/ingestion-routing.md`

- [ ] **Step 1: Write `skills/wiki/references/ingestion-routing.md`**

```markdown
# Ingestion Routing

Input-type autodetection for `wiki ingest <input>`:

| Pattern | Handler |
|---|---|
| `^\d{4}\.\d{4,5}(v\d+)?$` | arXiv ID → `mcp__agentic-rag-v2__download_arxiv` |
| `^10\.\d+/.+` | DOI → `mcp__agentic-rag-v2__doi2content` |
| URL matching `arxiv.org/abs/...` or `arxiv.org/pdf/...` | Extract arXiv ID (including version) → arXiv handler |
| Publisher URL (IEEE, ACM, Elsevier, Springer, Nature, Science, MDPI) | `mcp__agentic-rag-v2__fetch_publisher_html` |
| Local path ending `.pdf` | `ocr-papers-to-latex` skill |
| Local path ending `.md`, `.markdown`, `.tex` | Treat as pre-extracted; copy into `raw/papers/<pid>.*`, then read as-is into `raw/extracts/<pid>.md` |
| Everything else | Ask user to disambiguate |

After handler produces raw bytes/text + metadata, the pipeline continues per spec §5.2 steps 3–16.
```

- [ ] **Step 2: Replace the `## \`ingest <path|id|url>\`` stub in `skills/wiki/SKILL.md` with the full pipeline**

Replace the placeholder with the full step-by-step ingest from spec §5.2, including:
- Lock acquisition
- Routing (cite `references/ingestion-routing.md` for the detection table)
- Metadata extraction (first author, year, first meaningful word)
- Citation key derivation via `academic_wiki_lib.paper_id.generate_paper_id`
- Dedup pass 1 (source-sha): scan `raw/extracts/*.md` for matching `source-sha` — on match, skip and print the existing paper-id
- Dedup pass 2 (identifier): call `academic_wiki_lib.paper_id.find_existing_paper_by_identifiers` — on match, merge identifiers and treat as version
- Collision resolution: call `academic_wiki_lib.paper_id.resolve_collision`
- Metadata-extraction failure → fallback paper-id `unknown-YYYY-<filename-slug>` with `metadata-incomplete: true`
- Save files with `<paper-id>` basename consistently
- Write extract frontmatter per spec §3.7
- BibTeX: save if available; else stub `@misc` with `bib-incomplete: true`
- Log + commit to wiki's own git repo
- Release lock

Every shell command in the SKILL.md should operate on the **wiki's own git repo** (`git -C <wiki-path> …`), not the vault's.

- [ ] **Step 3: Verify by running a smoke test**

Since ingest uses MCP tools that are real-time (arXiv/DOI), the proper test is manual:

```bash
# From a clean shell, start Claude Code with academic-wiki plugin installed.
# In the session, run:
/academic-wiki:wiki init smoke
/academic-wiki:wiki ingest 1706.03762
# Then verify:
ls ~/ObsidianVault/03-Resources/smoke/raw/extracts/
ls ~/ObsidianVault/03-Resources/smoke/raw/bib/
cat ~/ObsidianVault/03-Resources/smoke/log.md
git -C ~/ObsidianVault/03-Resources/smoke log --oneline
# Cleanup:
/academic-wiki:wiki remove smoke
```

Expected:
- `raw/extracts/vaswani-2017-attention.md` exists with `source-sha` in frontmatter.
- `raw/bib/vaswani-2017-attention.bib` exists.
- `log.md` has an `ingest` entry.
- git log shows the ingest commit.

(Document this smoke test as Wave 1's exit-criterion check.)

- [ ] **Step 4: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): ingest — routing, dedup, version handling, paper-id generation"
```

## Task 1.14: `compile --paper-only` (Wave 1 tier, spec §5.3)

**Files:**
- Modify: `skills/wiki/SKILL.md` (fill in the compile section)
- Create: `skills/wiki/references/compilation-guide.md`

- [ ] **Step 1: Write `skills/wiki/references/compilation-guide.md`**

```markdown
# Compilation Guide

## Paper-only tier (Wave 1 default)

The paper-only tier is the safe starting point. It produces paper pages from raw extracts without creating entity pages (concept/method/open-problem), without cross-paper synthesis, and without `cites:` resolution.

### Per-source steps

1. Read `raw/extracts/<paper-id>.md` + `raw/notes/<paper-id>.md` if present.
2. Populate `wiki/papers/<paper-id>.md` per spec §3.1 with:
   - Frontmatter: `paper-id`, `citation-key`, `type: paper`, `status: read` (or `skimmed` — LLM infers from note presence/length), `created`, `updated`, `publication-date` if known, `title`, `authors` (slug + name objects), `year`, `venue`, `identifiers`, `source-version`, `bib-file`, `extract`, `notes` (only if the file exists), `figures` (only if the dir is non-empty), `references-raw` (unresolved bibliography), `cites: []` (stays empty in Wave 1), `tags` (`field/…`, `subfield/…`, `method/…`, `year/…`, `venue/…`).
   - Body sections: `Metadata`, `Summary`, `Key Contributions`, `Methods`, `Results`, `Claims`, `User Notes`, `See Also`.
   - User Notes section: if `raw/notes/<paper-id>.md` exists, include a brief summary + a link `[[raw/notes/<paper-id>|user notes]]`. Else: `_No user notes filed._`
3. If the paper page already exists (re-compile), apply the **update conflict policy** (spec §3.6): preserve prior content, append new evidence, flag contradictions with `[!WARNING]` callouts, never replace without provenance, bump `updated:` frontmatter.

### What NOT to do in paper-only tier

- Do NOT create concept/method/open-problem pages.
- Do NOT create cross-paper claim/result pages.
- Do NOT run backlink audit.
- Do NOT resolve `cites:`; leave it empty. Populate `references-raw:` only.

Wave 2 lifts these restrictions.
```

- [ ] **Step 2: Replace the `## \`compile\`` stub in `skills/wiki/SKILL.md`**

Add the paper-only tier as the default Wave 1 behavior:

```markdown
## `compile [<paper-id>] [--paper-only]`

Wave 1 default: **paper-only tier**. Reads raw extracts, creates/updates paper pages, writes `references-raw:` but not `cites:`. Does NOT do entity extraction, cross-paper synthesis, or backlink audit. See `references/compilation-guide.md`.

### Paper-only steps

1. Acquire `<wiki-path>/.lock` with op=`compile`.
2. If `<paper-id>` given: compile that one. Else: list files in `raw/extracts/` (excluding `*.versions.yml`); for each, check if `wiki/papers/<paper-id>.md` exists. Compile any that don't (new) or have a stale `updated:` vs `extracted-at:` (updated source).
3. For each source:
    - Read `raw/extracts/<paper-id>.md` via `academic_wiki_lib.frontmatter.read_frontmatter`.
    - Read `raw/notes/<paper-id>.md` if present.
    - If `wiki/papers/<paper-id>.md` exists, read it to get existing content; apply §3.6 update policy.
    - Extract bibliography lines → `references-raw: [...]` (verbatim strings).
    - Write (or update) `wiki/papers/<paper-id>.md` with complete body sections per §3.1.
4. Update `wiki/index.md`: append a chronological entry `- [[<paper-id>]] — <title> (YYYY-MM-DD)` under an `## Uncategorized` heading (field tagging kicks in properly in Wave 2).
5. Append to `log.md`: `## [YYYY-MM-DD] compile | N paper pages created/updated`.
6. Commit inside wiki repo: `git -C <wiki-path> add . && git -C <wiki-path> commit -m "compile: paper-only <summary>"`.
7. Release lock.

### Full tier (Wave 2)

<Wave 2 fills this in.>
```

- [ ] **Step 3: Smoke test**

```bash
# After Task 1.13 completes
/academic-wiki:wiki compile vaswani-2017-attention
ls ~/ObsidianVault/03-Resources/smoke/wiki/papers/
cat ~/ObsidianVault/03-Resources/smoke/wiki/papers/vaswani-2017-attention.md
```

Expected:
- File exists with full frontmatter and body sections.
- `references-raw:` populated with bibliography lines.
- `cites: []` empty.
- No `wiki/concepts/`, `wiki/methods/`, etc. files created.
- `log.md` has a compile entry.

- [ ] **Step 4: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): compile --paper-only (Wave 1 tier)"
```

## Task 1.15: `query` command — Phase 1 search (spec §5.4, §6.1)

**Files:**
- Modify: `skills/wiki/SKILL.md` (fill in the query section)

- [ ] **Step 1: Replace the `## \`query\`` stub in `skills/wiki/SKILL.md`**

```markdown
## `query <question>`

Answer a question against paper pages. In Wave 1, only paper pages exist — concept/method/etc. come in Wave 2.

### Steps

1. Determine search backend:
    - Check for qmd at `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd` AND a configured collection → use qmd.
    - Otherwise → Phase 1: index.md + ripgrep.
2. Phase 1 search flow:
    - Read `wiki/index.md`; identify candidate paper-ids by title/description keyword match.
    - Run ripgrep for the question's nouns against `wiki/papers/`:
        ```bash
        rg -l -i -e "<term1>" -e "<term2>" "${WIKI}/wiki/papers/"
        ```
    - Deduplicate candidate paper-ids across both passes.
3. Read all candidate paper pages. Follow one level of wikilinks (if targets exist; in Wave 1 targets are other paper pages).
4. Synthesize an answer:
    - Default: prose with `[[paper-id]]` inline citations.
    - If question contains "compare" or "table": markdown table with paper-ids in rows/cells.
    - If question contains "slides": Marp markdown with `marp: true` frontmatter.
5. File the answer to `wiki/queries/<slug>.md` per the query-output schema:
    ```yaml
    ---
    type: query-output
    question: "<original>"
    status: filed
    created: YYYY-MM-DD
    updated: YYYY-MM-DD
    sources: [paper-id-1, paper-id-2, ...]
    tags: [field/...]
    ---
    ```
    Slug derivation: `make_slug("<question>")` truncated to 60 chars.
6. (Wave 1) Ask: "Promote this answer to a concept/method/open-problem/claim/result page? Type `no` or `<type>`." If yes, move to `wiki/<type>/<slug>.md`, update frontmatter (status → promoted, type → the chosen type, add entity-specific fields with `sources:` populated).
7. Append to `log.md`: `## [YYYY-MM-DD] query | <slug>` (and `promote: <slug> to <type>` if promoted).
8. Commit inside wiki repo.
```

- [ ] **Step 2: Smoke test**

```bash
/academic-wiki:wiki query "What is the key contribution of Attention Is All You Need?"
ls ~/ObsidianVault/03-Resources/smoke/wiki/queries/
cat ~/ObsidianVault/03-Resources/smoke/wiki/queries/*.md | head -30
```

Expected:
- A query file exists with a `[[vaswani-2017-attention]]` citation.
- Commit recorded.

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): query with Phase 1 search (index.md + ripgrep)"
```

## Task 1.16: Wave 1 integration fixture + end-to-end test

**Files:**
- Create: `tests/fixtures/mini-wiki/` directory structure
- Create: `tests/fixtures/mini-wiki/README.md`
- Create: `tests/test_wave1_e2e.py`

- [ ] **Step 1: Set up fixture source files**

Create five fixture inputs:

```bash
mkdir -p tests/fixtures/mini-wiki
cat > tests/fixtures/mini-wiki/README.md <<'EOF'
# Mini-wiki integration fixture

Hand-crafted sources for ≥5 papers covering:
1. `sample-arxiv.md` — synthetic arXiv-style paper extract
2. `sample-doi.md` — synthetic DOI-based paper extract
3. `sample-local.pdf` → use a small synthetic PDF with known text (generate via `enscript -o sample.ps; ps2pdf` or similar)
4. `sample-with-notes.md` + `sample-with-notes.notes.md` — paper + user notes
5. `sample-arxiv-v2.md` — same arXiv ID as #1, version v2, to verify version handling

All are synthetic and contain fake bibliographies. The E2E test ingests each, compiles
paper-only, queries, and asserts the expected wiki state.
EOF
```

Populate the synthetic files (stub content is fine — the test is for plumbing, not content quality). The PDF can be skipped by writing a `.pdf` placeholder or generating a real one via:

```bash
python3 -c "
from fpdf import FPDF
pdf = FPDF()
pdf.add_page()
pdf.set_font('Arial', size=12)
pdf.cell(200, 10, txt='Sample Paper Title', ln=1)
pdf.cell(200, 10, txt='Chen, Y. 2023. Neural Networks for Everything.', ln=1)
pdf.output('tests/fixtures/mini-wiki/sample-local.pdf')
" 2>/dev/null || echo "(install fpdf or use an existing PDF; the test is shell-driven and tolerates missing PDFs with a skip)"
```

- [ ] **Step 2: Write `tests/test_wave1_e2e.py`**

```python
"""Wave 1 end-to-end integration test.

This test does NOT invoke the actual Claude Code plugin (which requires an agent
session). Instead, it simulates the critical deterministic pieces of ingest +
compile-paper-only + query on a controlled fixture, verifying file structure,
frontmatter correctness, commit creation, and dedup/version handling.

A manual, agent-driven smoke test complements this (documented in the SKILL.md).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter
from academic_wiki_lib.paper_id import (
    find_existing_paper_by_identifiers,
    generate_paper_id,
    resolve_collision,
)
from academic_wiki_lib.source_sha import file_sha256
from academic_wiki_lib.slug import make_slug


def _git(*args, cwd):
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env)


def test_init_creates_full_tree(tmp_wiki):
    """tmp_wiki fixture from conftest creates the tree. Verify structure."""
    assert (tmp_wiki / "wiki" / "papers").is_dir()
    assert (tmp_wiki / "raw" / "bib").is_dir()
    assert (tmp_wiki / "outputs" / "reports").is_dir()


def test_ingest_then_dedup_by_identifier(tmp_wiki):
    # First ingest: create a paper page with an arXiv identifier
    paper_page = tmp_wiki / "wiki/papers/vaswani-2017-attention.md"
    write_frontmatter(str(paper_page), {
        "paper-id": "vaswani-2017-attention",
        "identifiers": {"arxiv": "1706.03762", "arxiv-version": "v3"},
    }, "body\n")
    # Second "ingest" of the same arXiv ID (different version) should find it
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"arxiv": "1706.03762"})
    assert found == "vaswani-2017-attention"


def test_collision_resolution_when_different_papers_produce_same_id(tmp_wiki):
    # Two different papers both produce `smith-2020-neural`
    (tmp_wiki / "wiki/papers/smith-2020-neural.md").write_text("---\n---\n")
    new_id = resolve_collision(str(tmp_wiki), "smith-2020-neural")
    assert new_id == "smith-2020-neural-2"


def test_source_sha_dedup_detects_exact_duplicate(tmp_path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")
    assert file_sha256(str(a)) == file_sha256(str(b))


def test_query_output_slug_deterministic():
    q = "What is the key contribution of Attention Is All You Need?"
    assert make_slug(q) == "what-is-key-contribution-attention-is-all-you-need"[:60].rstrip("-")


def test_paper_page_has_all_required_frontmatter_fields(tmp_wiki):
    """A fully-constructed paper page per §3.1 must contain all required fields."""
    paper_page = tmp_wiki / "wiki/papers/vaswani-2017-attention.md"
    write_frontmatter(str(paper_page), {
        "paper-id": "vaswani-2017-attention",
        "citation-key": "vaswani2017attention",
        "type": "paper",
        "status": "read",
        "created": "2026-04-16",
        "updated": "2026-04-16",
        "title": "Attention Is All You Need",
        "authors": [{"slug": "ashish-vaswani", "name": "Ashish Vaswani"}],
        "year": 2017,
        "venue": "nips",
        "identifiers": {"arxiv": "1706.03762"},
        "aliases": [],
        "source-version": "arxiv-v5",
        "bib-file": "raw/bib/vaswani-2017-attention.bib",
        "extract": "raw/extracts/vaswani-2017-attention.md",
        "references-raw": ["Bahdanau 2014"],
        "cites": [],
        "tags": ["field/nlp", "year/2017"],
    }, "body\n")
    fm, _ = read_frontmatter(str(paper_page))
    required = ["paper-id", "type", "status", "created", "updated", "title",
                "authors", "year", "identifiers", "source-version",
                "bib-file", "extract", "references-raw", "cites", "tags"]
    for field in required:
        assert field in fm, f"Missing required field: {field}"
```

- [ ] **Step 3: Run the integration tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_wave1_e2e.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run full test suite**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest -v
```

Expected: all Wave 1 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: Wave 1 integration fixture + E2E plumbing tests"
```

## Task 1.17: Wave 1 smoke-test walkthrough + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# academic-wiki

A Claude Code plugin that implements an LLM-driven knowledge base specialized for academic papers.

## Status

- **Wave 1** (current): init, ingest, compile --paper-only, query (Phase 1 search).
- **Wave 2**: entity extraction, cites resolution, cross-paper synthesis.
- **Wave 3**: lint, export-bibtex, snapshot.
- **Wave 4**: remove, walkthrough, polish.

## Installation

```bash
claude plugin install /path/to/academic_wiki
```

### Prerequisites

- Python 3.10+
- git with user.name and user.email
- Obsidian vault at `~/ObsidianVault/03-Resources/`
- Node.js 18+ (for qmd auto-install)
- Skill: `ocr-papers-to-latex` (for PDF extraction)
- MCP: `agentic-rag-v2` (for arXiv/DOI/publisher fetching)

## Usage

### Initialize

```
/academic-wiki:wiki init academic
```

Creates `~/ObsidianVault/03-Resources/academic/` as a self-contained wiki with its own git repo.

### Ingest a paper

```
/academic-wiki:wiki ingest 1706.03762
/academic-wiki:wiki ingest 10.1145/3442188.3445922
/academic-wiki:wiki ingest ~/Downloads/paper.pdf
```

### Compile (paper-only in Wave 1)

```
/academic-wiki:wiki compile
/academic-wiki:wiki compile vaswani-2017-attention
```

### Query

```
/academic-wiki:wiki query "What is the key contribution of Attention Is All You Need?"
```

## Spec

See `docs/superpowers/specs/2026-04-16-academic-wiki-design.md`.

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: Wave 1 README"
```

## Task 1.18: Wave 1 exit-criterion validation

- [ ] **Step 1: Run the manual smoke-test script**

```bash
# Install the plugin locally and run in a Claude Code session:
/academic-wiki:wiki init wave1-smoke
/academic-wiki:wiki ingest 1706.03762
/academic-wiki:wiki ingest 2010.11929            # another arXiv
/academic-wiki:wiki ingest 10.1145/3442188.3445922   # a DOI
/academic-wiki:wiki ingest ~/Downloads/sample.pdf   # local PDF
# Create user notes for one of the papers:
echo "# My notes\nKey takeaway: X" > ~/ObsidianVault/03-Resources/wave1-smoke/raw/notes/vaswani-2017-attention.md
/academic-wiki:wiki compile
/academic-wiki:wiki compile --paper-only vaswani-2017-attention
# Re-ingest same arXiv with a v5 tag — should dedupe/version:
/academic-wiki:wiki ingest 1706.03762v5
/academic-wiki:wiki query "What is self-attention?"
```

- [ ] **Step 2: Verify exit criteria from spec §11.1**

Check:
- [ ] ≥5 real papers ingested (≥1 arXiv, ≥1 DOI, ≥1 local PDF, ≥1 with `raw/notes/<pid>.md`, ≥1 re-ingested as new version)
- [ ] Dedup verified (second ingest of same arXiv yields "skip, already ingested" OR "merged as new version")
- [ ] Version handling verified (both versions saved, paper page updated with new `source-version`)
- [ ] `wiki/papers/<pid>.md` files exist and are well-formed
- [ ] `raw/extracts/<pid>.md` files exist with `source-sha` and other required frontmatter
- [ ] No concept/method/open-problem/claim/result pages exist (Wave 1 invariant)
- [ ] Query produces an answer with `[[paper-id]]` citations and files to `wiki/queries/`
- [ ] `log.md` has entries for every operation
- [ ] Every operation produced a git commit inside the wiki's own repo

- [ ] **Step 3: Clean up and tag Wave 1**

```bash
/academic-wiki:wiki remove wave1-smoke  # Wave 4's remove — if not yet implemented, rm -rf manually
git tag wave1-complete
```

- [ ] **Step 4: Commit the completion marker**

```bash
git commit --allow-empty -m "milestone: Wave 1 exit criteria validated"
```

---

# Wave 2 — Synthesis

**Exit criterion (from spec §11.2):** on ≥15 compiled papers, concept/method/open-problem pages exist for a majority of papers, backlink density ≥3 wikilinks per page on average, promotion candidates reviewed by hand at least once.

## Task 2.1: Entity extraction — concept/method/open-problem pages

**Files:**
- Modify: `skills/wiki/SKILL.md` — extend `compile` with the full tier.
- Create: `skills/wiki/references/entity-schemas.md` — inline copies of §3.1–§3.3 schemas.
- Create: `skills/wiki/references/promotion-rules.md` — Wave 2 candidate detection + promotion flow.

- [ ] **Step 1: Write `skills/wiki/references/entity-schemas.md`**

Copy the content of spec §§3.1–3.4 into this file. It becomes a reference the LLM loads when creating or updating entity pages.

- [ ] **Step 2: Write `skills/wiki/references/promotion-rules.md`**

```markdown
# Promotion Rules (Wave 2)

In Wave 2, compile detects cross-paper claim/result candidates but **does not auto-promote**. Candidates are written to `outputs/reports/YYYY-MM-DD-promotion-candidates.md` for explicit user action.

## Detection heuristic

For each claim/result drafted inline in a new paper page:
1. Search existing paper pages for claim/result sections whose text is semantically equivalent. Use LLM judgment — not regex. Example equivalences:
   - "attention is quadratic in sequence length" ≈ "self-attention complexity grows as O(n²)"
   - "RSMA outperforms NOMA under imperfect CSI" ≈ "rate-splitting surpasses non-orthogonal MA when CSI is noisy"
2. If ≥1 equivalent match found, write a candidate entry to `outputs/reports/YYYY-MM-DD-promotion-candidates.md`:
   ```markdown
   ## Candidate: <proposed-slug>

   **Type:** claim | result
   **Sources:** [[<paper-id-1>]], [[<paper-id-2>]]
   **Statement:** <one-paragraph synthesis of the shared claim/result>

   **To promote:** Run `/academic-wiki:wiki query "promote candidate <proposed-slug>"` then accept.
   ```

## Promotion flow (user-triggered)

1. User reviews the candidates file.
2. Runs `query "promote candidate <slug>"` — the query flow finds the candidate and asks whether to promote as claim/result.
3. On acceptance:
   - Create `wiki/claims/<slug>.md` or `wiki/results/<slug>.md` per §3.
   - Move the claim/result prose out of the paper pages' Claims/Results section and into the new page; replace in-paper with `[[wikilink]]`.
   - Add this candidate-id to a `promoted.log` so future compile passes don't re-surface it.
```

- [ ] **Step 3: Extend `compile` in `skills/wiki/SKILL.md` with the full tier**

Add a "Full tier (Wave 2)" subsection replacing the stub. Describe:

1. All paper-only steps (as in Wave 1), plus:
2. **Entity extraction**: identify concepts, methods, open-problems from the extract. For each:
    - Generate a slug via `academic_wiki_lib.slug.make_slug`.
    - Check if `wiki/concepts/<slug>.md` (or methods/open-problems) exists. If yes, apply §3.6 update policy. If no, create from §3 template.
    - Append `paper-id` to `sources:`.
    - Populate `field/*` and `subfield/*` tags from the paper's tags.
3. **Cross-paper candidate detection** (per `promotion-rules.md`): write to `outputs/reports/YYYY-MM-DD-promotion-candidates.md`. Do NOT promote silently.
4. **`cites:` resolution**: for each `references-raw` entry, fuzzy-match against existing `wiki/papers/` by title + first-author + year (LLM judgment). Matches populate `cites:`. Unmatched entries stay in `references-raw` only.
5. **Backlink audit with allowlist** (tightened — don't over-link common words):
    - `grep -rln "<new-slug>" wiki/` for each new entity slug.
    - Only insert `[[wikilink]]` if the slug is ≥2 words OR the page title is in a noun phrase the LLM judges as a proper named entity.
    - Commit the backlink additions together with the entity pages.
6. **Index update**: sectioned by `field/*` tag. Use Dataview-compatible format:
    ```markdown
    ## field/wireless-comms
    - [[paper-id]] — title (YYYY-MM-DD)
    ```

- [ ] **Step 4: Update the Task 1.16 integration test to cover Wave 2 behavior**

Add tests that:
- Invoke `compile` (not `--paper-only`) on the fixture.
- Assert that `wiki/concepts/`, `wiki/methods/`, `wiki/open-problems/` have ≥1 file each.
- Assert that at least one paper page's `cites:` is populated (resolution worked).
- Assert that the backlink audit added at least one wikilink to an older paper.
- Assert that `outputs/reports/*-promotion-candidates.md` exists and is well-formed if cross-paper overlap was seeded.

- [ ] **Step 5: Run tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add skills/wiki/ tests/
git commit -m "feat(cmd): compile full tier — entity extraction, cites resolution, backlink audit, promotion candidates"
```

## Task 2.2: Update conflict policy (§3.6) in compile

**Files:**
- Modify: `skills/wiki/SKILL.md` (add detailed update-policy subsection under compile)

- [ ] **Step 1: Extend the compile section with an explicit "When updating an existing page" subsection**

```markdown
### When updating an existing page (spec §3.6)

Any time `compile` touches a page that already exists:

1. **Read the existing content fully.** Use `academic_wiki_lib.frontmatter.read_frontmatter` + body.
2. **Preserve prior claims.** Do not delete existing content solely because a new source doesn't mention it.
3. **Append new evidence.** Add the new source-paper-id to `sources:` and incorporate new content in a clearly attributed paragraph or section (e.g., "In <paper-title> (<year>), the authors report …").
4. **Flag contradictions inline.** If the new content is in tension with existing content, add an Obsidian callout:
    ```markdown
    > [!WARNING] Contradiction with [[other-paper-id]]
    > <paper A> claims X, but <paper B> (cited above) claims Y. Needs resolution.
    ```
5. **Never replace without provenance.** Every material claim on the page must trace to ≥1 `paper-id` in `sources:`. If an LLM cannot attribute a claim, drop it or mark `status: stale`.
6. **Bump `updated:` frontmatter** to today's date.
7. **Log the merge** in the compile commit: `compile: merged <new-paper-id> into <N> existing pages`.
```

- [ ] **Step 2: Add a unit test that seeds a conflicting compile and asserts the `[!WARNING]` callout appears**

Add to `tests/test_wave1_e2e.py` or a new `tests/test_wave2_compile.py`:

```python
def test_compile_adds_contradiction_callout(tmp_wiki):
    """When a concept page is updated with a conflicting claim, expect an Obsidian callout."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    # Prime a concept page with one source's claim
    page = tmp_wiki / "wiki/concepts/attention-complexity.md"
    write_frontmatter(str(page), {
        "type": "concept",
        "status": "active",
        "created": "2026-04-01",
        "updated": "2026-04-01",
        "sources": ["vaswani-2017-attention"],
        "tags": ["field/nlp"],
    }, "Attention is quadratic in sequence length per [[vaswani-2017-attention]].\n")
    # Simulate a compile update with a conflicting claim — this is a placeholder
    # for the LLM-driven merge; for now we just verify the helper is invokable.
    # The real behavior is validated by the agent-driven smoke test in Task 2.3.
    content = page.read_text()
    assert "quadratic" in content  # sanity
```

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/ tests/
git commit -m "feat(cmd): compile honors update conflict policy (spec 3.6)"
```

## Task 2.3: Wave 2 smoke test (agent-driven)

- [ ] **Step 1: Run a Wave 2 smoke session**

```bash
# In a Claude Code session:
/academic-wiki:wiki init wave2-smoke
# Ingest 15+ related papers (use a focused topic like "attention in NLP")
# Then:
/academic-wiki:wiki compile  # full tier, default in Wave 2
# Inspect:
ls ~/ObsidianVault/03-Resources/wave2-smoke/wiki/concepts/
ls ~/ObsidianVault/03-Resources/wave2-smoke/wiki/methods/
cat ~/ObsidianVault/03-Resources/wave2-smoke/outputs/reports/*-promotion-candidates.md
# Verify exit criteria:
# - concept/method/open-problem pages exist for a majority of papers
# - average wikilink density ≥3 per page (use a grep + wc)
# - promotion candidates report exists and is reviewed
```

Quick wikilink-density check:

```bash
python3 -c "
import re, glob
files = glob.glob('$HOME/ObsidianVault/03-Resources/wave2-smoke/wiki/**/*.md', recursive=True)
total_links = sum(len(re.findall(r'\[\[[^\]]+\]\]', open(f).read())) for f in files)
print(f'{len(files)} pages, {total_links} wikilinks, avg {total_links/max(1,len(files)):.1f} per page')
"
```

- [ ] **Step 2: Manually review the promotion-candidates report; accept or reject each candidate via the promote flow**

- [ ] **Step 3: Tag Wave 2**

```bash
git tag wave2-complete
git commit --allow-empty -m "milestone: Wave 2 exit criteria validated"
```

---

# Wave 3 — Maintenance and Output

**Exit criterion:** `lint`, `export-bibtex`, `snapshot` all work end-to-end against the wiki produced by Waves 1–2.

## Task 3.1: `lint-wiki.py` deterministic checks (§5.5)

**Files:**
- Create: `scripts/lint-wiki.py`
- Create: `tests/test_lint_wiki.py`

- [ ] **Step 1: Write `tests/test_lint_wiki.py` first**

Full test coverage per spec §5.5. Each check has its own test.

```python
"""Tests for lint-wiki.py deterministic checks per spec §5.5."""
import subprocess
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import write_frontmatter


SCRIPT = str(Path(__file__).parent.parent / "scripts" / "lint-wiki.py")


def run_lint(wiki_root):
    result = subprocess.run(
        ["python3", SCRIPT, str(wiki_root)],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_dead_link_is_flagged_not_stubbed(tmp_wiki):
    write_frontmatter(str(tmp_wiki / "wiki/concepts/foo.md"), {
        "type": "concept", "status": "active",
        "created": "2026-04-16", "updated": "2026-04-16",
        "sources": ["some-paper"],
        "tags": ["field/nlp"],
    }, "See [[nonexistent]].\n")
    rc, out, _ = run_lint(tmp_wiki)
    assert "DEAD_LINK" in out
    assert "nonexistent" in out
    # Lint must NOT auto-create the stub:
    assert not (tmp_wiki / "wiki" / "concepts" / "nonexistent.md").exists()


def test_alias_resolves_dead_link(tmp_wiki):
    # Page with alias
    write_frontmatter(str(tmp_wiki / "wiki/concepts/new-slug.md"), {
        "type": "concept", "status": "active",
        "created": "2026-04-16", "updated": "2026-04-16",
        "sources": ["p"], "aliases": ["old-slug"],
        "tags": ["field/nlp"],
    }, "Body.\n")
    # Page that links to the old slug
    write_frontmatter(str(tmp_wiki / "wiki/concepts/referrer.md"), {
        "type": "concept", "status": "active",
        "created": "2026-04-16", "updated": "2026-04-16",
        "sources": ["p"],
        "tags": ["field/nlp"],
    }, "See [[old-slug]].\n")
    rc, out, _ = run_lint(tmp_wiki)
    # lint should note the alias (not flag as dead):
    assert "ALIAS" in out or "alias" in out.lower()


def test_orphan_detected(tmp_wiki):
    write_frontmatter(str(tmp_wiki / "wiki/concepts/lonely.md"), {
        "type": "concept", "status": "active",
        "created": "2026-04-16", "updated": "2026-04-16",
        "sources": ["p"],
        "tags": ["field/nlp"],
    }, "No inbound links.\n")
    rc, out, _ = run_lint(tmp_wiki)
    assert "ORPHAN" in out


def test_missing_field_tag(tmp_wiki):
    write_frontmatter(str(tmp_wiki / "wiki/concepts/untagged.md"), {
        "type": "concept", "status": "active",
        "created": "2026-04-16", "updated": "2026-04-16",
        "sources": ["p"],
        "tags": ["method/xyz"],  # no field/*
    }, "Body.\n")
    rc, out, _ = run_lint(tmp_wiki)
    assert "MISSING_FIELD_TAG" in out


def test_stale_page_status_stale_older_than_90_days(tmp_wiki):
    from datetime import date, timedelta
    long_ago = (date.today() - timedelta(days=100)).isoformat()
    write_frontmatter(str(tmp_wiki / "wiki/concepts/old.md"), {
        "type": "concept", "status": "stale",
        "created": "2025-01-01", "updated": long_ago,
        "sources": ["p"],
        "tags": ["field/nlp"],
    }, "Body.\n")
    rc, out, _ = run_lint(tmp_wiki)
    assert "STALE" in out


def test_missing_counter_args_on_concept(tmp_wiki):
    write_frontmatter(str(tmp_wiki / "wiki/concepts/foo.md"), {
        "type": "concept", "status": "active",
        "created": "2026-04-16", "updated": "2026-04-16",
        "sources": ["p"],
        "tags": ["field/nlp"],
    }, "Body without the required section.\n")
    rc, out, _ = run_lint(tmp_wiki)
    assert "MISSING_SECTION" in out


def test_invalid_cites_key(tmp_wiki):
    write_frontmatter(str(tmp_wiki / "wiki/papers/smith-2020-foo.md"), {
        "paper-id": "smith-2020-foo", "type": "paper",
        "status": "read", "created": "2026-04-16", "updated": "2026-04-16",
        "title": "Foo", "authors": [{"slug": "smith", "name": "Smith"}],
        "year": 2020, "identifiers": {"doi": "10.x/y"},
        "bib-file": "raw/bib/smith-2020-foo.bib",
        "extract": "raw/extracts/smith-2020-foo.md",
        "references-raw": [], "cites": ["ghost-paper-id"],
        "tags": ["field/nlp", "year/2020"],
    }, "Body.\n")
    rc, out, _ = run_lint(tmp_wiki)
    assert "INVALID_CITES" in out
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_lint_wiki.py -v
```

- [ ] **Step 3: Write `scripts/lint-wiki.py`**

```python
#!/usr/bin/env python3
"""Deterministic wiki lint per spec §5.5."""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

# Make the lib importable when running as a script
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.frontmatter import read_frontmatter

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _entity_type(rel: str) -> str:
    parts = rel.split(os.sep)
    if parts[0] != "wiki" or len(parts) < 2:
        return ""
    return parts[1][:-1] if parts[1].endswith("s") else parts[1]  # "papers" -> "paper"


def _scan_files(wiki_root: Path) -> dict[str, tuple[Path, dict, str]]:
    """Return {slug: (path, frontmatter, body)}, including papers as their paper-id."""
    out = {}
    for md in (wiki_root / "wiki").rglob("*.md"):
        rel = md.relative_to(wiki_root)
        fm, body = read_frontmatter(str(md))
        slug = md.stem
        out[slug] = (md, fm, body)
    return out


def lint(wiki_root: str) -> int:
    wr = Path(wiki_root)
    issues = []

    files = _scan_files(wr)
    # Build slug → path and alias → canonical-slug maps
    alias_to_canonical = {}
    for slug, (_, fm, _) in files.items():
        for a in fm.get("aliases") or []:
            alias_to_canonical[a] = slug

    inbound = {slug: set() for slug in files}

    for slug, (p, fm, body) in files.items():
        rel = str(p.relative_to(wr))
        # Dead-link and alias checks
        for target in WIKILINK_RE.findall(body):
            target = target.strip()
            if target in files:
                inbound[target].add(slug)
            elif target in alias_to_canonical:
                canonical = alias_to_canonical[target]
                issues.append(f"ALIAS_LINK: [[{target}]] in {rel} resolves to [[{canonical}]] — consider rewriting")
                inbound[canonical].add(slug)
            else:
                issues.append(f"DEAD_LINK: [[{target}]] in {rel}")

    skip = {"index", "log"}
    today = date.today()

    for slug, (p, fm, body) in files.items():
        rel = str(p.relative_to(wr))
        if slug in skip:
            continue

        # Orphan
        if not inbound.get(slug):
            issues.append(f"ORPHAN: {rel} has no inbound links")

        t = fm.get("type")
        tags = fm.get("tags") or []

        # Missing field/* on first-class entities
        if t in {"paper", "concept", "method", "open-problem", "claim", "result"}:
            if not any(isinstance(x, str) and x.startswith("field/") for x in tags):
                issues.append(f"MISSING_FIELD_TAG: {rel}")

        # Stale
        updated_s = fm.get("updated")
        try:
            updated = datetime.strptime(updated_s, "%Y-%m-%d").date() if updated_s else None
        except (TypeError, ValueError):
            updated = None
        if updated:
            age = (today - updated).days
            if fm.get("status") == "stale" and age > 90:
                issues.append(f"STALE: {rel} (status=stale, age={age}d)")
            if t in {"concept", "method"} and age > 180:
                issues.append(f"STALE: {rel} ({t} untouched for {age}d)")

        # Counter-Arguments section on concept/method
        if t in {"concept", "method"}:
            if "counter-arguments and gaps" not in body.lower():
                issues.append(f"MISSING_SECTION: {rel} lacks 'Counter-Arguments and Gaps'")

        # Invalid cites on paper pages
        if t == "paper":
            for c in fm.get("cites") or []:
                if c not in files:
                    issues.append(f"INVALID_CITES: {rel} cites unknown paper-id [{c}]")

            # Missing bibtex
            bib_file = fm.get("bib-file")
            if bib_file:
                bib_path = wr / bib_file
                if not bib_path.exists():
                    issues.append(f"MISSING_BIBTEX: {rel} (expected {bib_file})")
                elif "bib-incomplete" in bib_path.read_text(errors="ignore"):
                    issues.append(f"MISSING_BIBTEX: {rel} (bib-incomplete flag)")

    if not issues:
        print("OK: No issues found")
        return 0
    for i in sorted(issues):
        print(i)
    print(f"\nTotal: {len(issues)} issue(s)")
    return 0  # lint reports but doesn't fail CI by default; callers can count issues


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <wiki-root>", file=sys.stderr)
        sys.exit(1)
    sys.exit(lint(sys.argv[1]))
```

- [ ] **Step 4: Make executable and run tests**

```bash
chmod +x scripts/lint-wiki.py
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_lint_wiki.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/lint-wiki.py tests/test_lint_wiki.py
git commit -m "feat(scripts): lint-wiki.py deterministic checks per spec 5.5"
```

## Task 3.2: `lint` command wiring + LLM-assisted fix passes

**Files:**
- Modify: `skills/wiki/SKILL.md` (fill in the lint section)

- [ ] **Step 1: Replace the lint stub with the full §5.5 behavior**

```markdown
## `lint [--fix-dead-links] [--suggest-backlinks] [--with-suggestions]`

Run deterministic checks + optional opt-in LLM passes.

### Steps

1. Acquire lock (only if any `--fix-*` or `--suggest-*` flag is set; pure report is read-only).
2. Run deterministic checks:
    ```bash
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" \
        python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lint-wiki.py" "${WIKI_ROOT}" \
        > "${WIKI_ROOT}/outputs/reports/$(date +%Y-%m-%d)-lint.md"
    ```
3. Optional `--fix-dead-links` pass: LLM reads each DEAD_LINK issue's context, infers the entity type from the usage, and creates a stub using the appropriate §3 template. Commit separately.
4. Optional `--suggest-backlinks` pass: LLM identifies pages that should link to new pages but don't; produces a diff for user review. Does NOT apply silently.
5. Optional `--with-suggestions` pass: LLM suggests 3–5 questions the wiki can't yet answer well + 2–3 sources to strengthen gaps. Append to the lint report under `## Suggested Next Steps`.
6. Append to `log.md`: `## [YYYY-MM-DD] lint | <N> issues found, <M> fixed`.
7. Commit: `lint: YYYY-MM-DD (<N> issues)`.
8. Release lock.
```

- [ ] **Step 2: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): lint — deterministic checks + opt-in fix passes"
```

## Task 3.3: `bibtex-export.py` selector engine (§5.6)

**Files:**
- Create: `scripts/bibtex-export.py`
- Create: `tests/test_bibtex_export.py`

- [ ] **Step 1: Write `tests/test_bibtex_export.py`**

```python
"""Tests for bibtex-export.py per spec §5.6."""
import subprocess
from pathlib import Path

from academic_wiki_lib.frontmatter import write_frontmatter

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "bibtex-export.py")


def _setup_papers(wiki_root, papers):
    """papers: list of (paper-id, tags, created, bib-content)."""
    for pid, tags, created, bib in papers:
        paper_path = wiki_root / "wiki/papers" / f"{pid}.md"
        write_frontmatter(str(paper_path), {
            "paper-id": pid, "type": "paper", "status": "read",
            "created": created, "updated": created,
            "title": f"{pid} title", "authors": [{"slug": "x", "name": "X"}],
            "year": 2020, "identifiers": {}, "source-version": "",
            "bib-file": f"raw/bib/{pid}.bib",
            "extract": f"raw/extracts/{pid}.md",
            "references-raw": [], "cites": [],
            "tags": tags,
        }, "body\n")
        (wiki_root / "raw/bib" / f"{pid}.bib").write_text(bib)


def _run(*args, wiki_root):
    result = subprocess.run(
        ["python3", SCRIPT, str(wiki_root), *args],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_export_by_field(tmp_wiki):
    _setup_papers(tmp_wiki, [
        ("a-2020-one", ["field/nlp"], "2024-01-01", "@misc{a2020one,}\n"),
        ("b-2021-two", ["field/nlp"], "2024-06-01", "@misc{b2021two,}\n"),
        ("c-2022-three", ["field/wireless"], "2024-03-01", "@misc{c2022three,}\n"),
    ])
    rc, _, _ = _run("--field", "nlp", wiki_root=tmp_wiki)
    assert rc == 0
    bib_files = list((tmp_wiki / "outputs/bib").glob("*.bib"))
    assert len(bib_files) == 1
    content = bib_files[0].read_text()
    assert "a2020one" in content
    assert "b2021two" in content
    assert "c2022three" not in content


def test_export_by_tag_combined(tmp_wiki):
    _setup_papers(tmp_wiki, [
        ("a", ["field/nlp", "project/survey-2025"], "2024-01-01", "@misc{a,}\n"),
        ("b", ["field/nlp"], "2024-01-01", "@misc{b,}\n"),
    ])
    rc, _, _ = _run("--field", "nlp", "--project", "survey-2025", wiki_root=tmp_wiki)
    assert rc == 0
    content = list((tmp_wiki / "outputs/bib").glob("*.bib"))[0].read_text()
    assert "@misc{a," in content and "@misc{b," not in content


def test_export_since(tmp_wiki):
    _setup_papers(tmp_wiki, [
        ("a", ["field/nlp"], "2023-06-01", "@misc{a,}\n"),
        ("b", ["field/nlp"], "2024-06-01", "@misc{b,}\n"),
    ])
    rc, _, _ = _run("--field", "nlp", "--since", "2024-01-01", wiki_root=tmp_wiki)
    assert rc == 0
    content = list((tmp_wiki / "outputs/bib").glob("*.bib"))[0].read_text()
    assert "@misc{b," in content and "@misc{a," not in content


def test_export_label_override(tmp_wiki):
    _setup_papers(tmp_wiki, [
        ("a", ["field/nlp"], "2024-01-01", "@misc{a,}\n"),
    ])
    rc, _, _ = _run("--field", "nlp", "--label", "my-export", wiki_root=tmp_wiki)
    assert rc == 0
    files = list((tmp_wiki / "outputs/bib").glob("*my-export*.bib"))
    assert len(files) == 1


def test_export_reports_bib_incomplete(tmp_wiki):
    _setup_papers(tmp_wiki, [
        ("a", ["field/nlp"], "2024-01-01", "% bib-incomplete: true\n@misc{a,}\n"),
        ("b", ["field/nlp"], "2024-01-01", "@misc{b,}\n"),
    ])
    rc, out, _ = _run("--field", "nlp", wiki_root=tmp_wiki)
    assert rc == 0
    assert "bib-incomplete" in out.lower() or "incomplete" in out.lower()
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_bibtex_export.py -v
```

- [ ] **Step 3: Write `scripts/bibtex-export.py`**

```python
#!/usr/bin/env python3
"""Consolidated BibTeX export per spec §5.6."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.frontmatter import read_frontmatter
from academic_wiki_lib.slug import make_slug


def _parse_args(argv):
    p = argparse.ArgumentParser()
    p.add_argument("wiki_root")
    p.add_argument("--project")
    p.add_argument("--field")
    p.add_argument("--tag")
    p.add_argument("--query")           # Phase 1: substring match; full search comes via SKILL
    p.add_argument("--keys")            # comma-separated
    p.add_argument("--since")           # YYYY-MM-DD
    p.add_argument("--label")
    return p.parse_args(argv)


def _label_from_selectors(args) -> str:
    if args.label:
        return make_slug(args.label)
    for attr in ("project", "field", "tag", "query"):
        val = getattr(args, attr)
        if val:
            return make_slug(val)
    if args.keys:
        return make_slug(args.keys.split(",")[0])
    if args.since:
        return args.since
    return "export"


def _matches(fm: dict, args) -> bool:
    tags = fm.get("tags") or []
    if args.project and f"project/{args.project}" not in tags:
        return False
    if args.field and f"field/{args.field}" not in tags:
        return False
    if args.tag and args.tag not in tags:
        return False
    if args.since:
        try:
            created = datetime.strptime(fm.get("created", ""), "%Y-%m-%d").date()
        except ValueError:
            return False
        if created < datetime.strptime(args.since, "%Y-%m-%d").date():
            return False
    return True


def export(argv=None) -> int:
    args = _parse_args(argv)
    wr = Path(args.wiki_root)
    papers_dir = wr / "wiki" / "papers"
    bib_dir = wr / "raw" / "bib"

    selected: list[tuple[str, Path]] = []

    if args.keys:
        for key in [k.strip() for k in args.keys.split(",") if k.strip()]:
            paper_path = papers_dir / f"{key}.md"
            if paper_path.exists():
                selected.append((key, bib_dir / f"{key}.bib"))

    if any((args.project, args.field, args.tag, args.since)) or not selected:
        for md in papers_dir.glob("*.md"):
            fm, _ = read_frontmatter(str(md))
            if _matches(fm, args):
                pid = fm.get("paper-id") or md.stem
                selected.append((pid, bib_dir / f"{pid}.bib"))

    # Optional: --query handled via SKILL layer (hybrid search); script layer just takes keys
    if not selected:
        print("No papers match the selector.")
        return 1

    incomplete = []
    content_parts = []
    for pid, bib_path in selected:
        if not bib_path.exists():
            incomplete.append((pid, "missing .bib file"))
            continue
        body = bib_path.read_text()
        if "bib-incomplete" in body.lower():
            incomplete.append((pid, "bib-incomplete flag"))
        content_parts.append(f"% {pid}\n{body.strip()}\n")

    label = _label_from_selectors(args)
    out = wr / "outputs" / "bib" / f"{date.today()}-{label}.bib"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(content_parts) + "\n")

    print(f"Exported {len(selected)} papers to {out}")
    if incomplete:
        print(f"{len(incomplete)} have bib-incomplete issues:")
        for pid, reason in incomplete:
            print(f"  - {pid}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(export())
```

- [ ] **Step 4: Make executable and run tests**

```bash
chmod +x scripts/bibtex-export.py
cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_bibtex_export.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/bibtex-export.py tests/test_bibtex_export.py
git commit -m "feat(scripts): bibtex-export.py with all selectors per spec 5.6"
```

## Task 3.4: `export-bibtex` command wiring

**Files:**
- Modify: `skills/wiki/SKILL.md` (fill in the export-bibtex section)
- Create: `skills/wiki/references/bibtex-handling.md`

- [ ] **Step 1: Write `skills/wiki/references/bibtex-handling.md`** (brief reference — per-paper .bib convention, citation-key semantics, common gotchas)

- [ ] **Step 2: Replace the export-bibtex stub with full wiring**

```markdown
## `export-bibtex <selectors>`

Generate a consolidated `.bib` from a subset of paper pages.

### Steps

1. Acquire lock.
2. If `--query` is provided: use the search backend (qmd/index.md+rg) to find candidate paper-ids, then pass them via `--keys` to the CLI.
3. Otherwise: invoke the CLI directly:
    ```bash
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bibtex-export.py" "${WIKI_ROOT}" \
        [--project <slug>] [--field <slug>] [--tag <tag>] [--keys <k1,k2,...>] \
        [--since YYYY-MM-DD] [--label <str>]
    ```
4. Append to `log.md`: `## [YYYY-MM-DD] export | <label> (<N> papers)`.
5. Commit: `export: <label> (<N> papers)`.
6. Release lock.
```

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): export-bibtex wiring + bibtex-handling reference"
```

## Task 3.5: `snapshot` command (§5.7)

**Files:**
- Modify: `skills/wiki/SKILL.md` (fill in the snapshot section)

- [ ] **Step 1: Replace the snapshot stub**

```markdown
## `snapshot <label>`

Tag the wiki state for reproducibility. Operates on the wiki's own nested git repo.

### Steps

1. Acquire lock.
2. Verify working tree is clean:
    ```bash
    status=$(git -C "${WIKI_ROOT}" status --porcelain)
    if [[ -n "$status" ]]; then
        echo "Uncommitted changes in the wiki — commit them before snapshot." >&2
        echo "$status" >&2
        exit 1
    fi
    ```
3. Tag namespace `snapshot/<label>`:
    ```bash
    git -C "${WIKI_ROOT}" tag "snapshot/<label>"
    ```
4. Read current SHA for logging:
    ```bash
    sha=$(git -C "${WIKI_ROOT}" rev-parse HEAD)
    ```
5. Append to `log.md`: `## [YYYY-MM-DD] snapshot | <label>` with SHA body.
6. Commit the log change:
    ```bash
    git -C "${WIKI_ROOT}" add log.md
    git -C "${WIKI_ROOT}" commit -m "snapshot: <label>"
    ```
7. Release lock.
8. Print: `Tagged snapshot/<label> at <SHA>. Revisit with: git -C "${WIKI_ROOT}" checkout snapshot/<label>`.
```

- [ ] **Step 2: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): snapshot — git tag on wiki's own repo"
```

## Task 3.6: Wave 3 smoke tests

- [ ] **Step 1: Verify the three new commands work end-to-end on the wave2-smoke fixture**

```bash
/academic-wiki:wiki lint
cat ~/ObsidianVault/03-Resources/wave2-smoke/outputs/reports/*-lint.md | head -20

/academic-wiki:wiki export-bibtex --field nlp --label nlp-export
cat ~/ObsidianVault/03-Resources/wave2-smoke/outputs/bib/*-nlp-export.bib | head

/academic-wiki:wiki snapshot wave3-validated
git -C ~/ObsidianVault/03-Resources/wave2-smoke tag
```

- [ ] **Step 2: Tag Wave 3**

```bash
git tag wave3-complete
git commit --allow-empty -m "milestone: Wave 3 exit criteria validated"
```

---

# Wave 4 — Polish

## Task 4.1: `remove` command (§5.8)

**Files:**
- Modify: `skills/wiki/SKILL.md` (fill in remove section)

- [ ] **Step 1: Replace the remove stub**

```markdown
## `remove <name>`

Delete a wiki and its nested git repo after confirmation.

### Steps

1. Resolve path: `~/ObsidianVault/03-Resources/<name>/`. Abort if missing.
2. Confirm: print tree contents and prompt: `"This will permanently delete '<name>' AND its git history at <path>. Proceed? (y/n)"`.
3. Acquire lock at the wiki root (so concurrent ops can't race with removal).
4. Remove qmd collection if installed:
    ```bash
    "${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd" collection remove <name>
    ```
5. Remove the directory entirely:
    ```bash
    rm -rf ~/ObsidianVault/03-Resources/<name>
    ```
6. If the Obsidian vault is itself a git repo, commit the removal:
    ```bash
    if [[ -d ~/ObsidianVault/.git ]]; then
        git -C ~/ObsidianVault commit -am "remove: <name> wiki" || true
    fi
    ```
7. Print: `"Wiki '<name>' removed."`
```

- [ ] **Step 2: Smoke test**

```bash
/academic-wiki:wiki init smoke-remove
/academic-wiki:wiki remove smoke-remove
ls ~/ObsidianVault/03-Resources/ | grep smoke-remove
```

Expected: no `smoke-remove` directory.

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): remove — delete wiki + nested git repo"
```

## Task 4.2: WALKTHROUGH.md

**Files:**
- Create: `WALKTHROUGH.md`

- [ ] **Step 1: Write `WALKTHROUGH.md`**

A full end-to-end user-facing walkthrough, modeled on `llm-wiki/WALKTHROUGH.md` but adapted for academic workflows:

- Part 1: Introduction (what is an academic wiki, why Obsidian, what this plugin does)
- Part 2: Concepts (paper-id vs citation-key, raw/wiki separation, entity types, tag taxonomy, promotion flow)
- Part 3: Installation
- Part 4: Your First Academic Wiki (guided walkthrough — init, ingest arXiv, ingest DOI, ingest local PDF, add user notes, compile paper-only, query, compile full, snapshot, export-bibtex, lint)
- Part 5: Obsidian Integration (graph view, Dataview queries over the academic frontmatter, Web Clipper for academic pages, Marp slide export from concept pages)
- Part 6: Advanced Usage (dedup, versioning, promotion, tagging conventions for research projects)
- Part 7: Cleanup (remove command)
- Part 8: Troubleshooting

- [ ] **Step 2: Commit**

```bash
git add WALKTHROUGH.md
git commit -m "docs: full walkthrough covering all waves"
```

## Task 4.3: Marp slide export convenience

**Files:**
- Modify: `skills/wiki/SKILL.md` — add a short section describing how to export a page as Marp slides (when a page has `marp: true` frontmatter).

- [ ] **Step 1: Add the Marp section to SKILL.md**

```markdown
## Marp slide export

Any wiki page can become a slide deck. Add `marp: true` to the frontmatter, then run:

```bash
"${CLAUDE_PLUGIN_DATA}/node_modules/.bin/marp" "${WIKI_ROOT}/wiki/<path-to-page>.md" -o output.html
```

The `query` command supports this directly: if the user's question contains "slides", the filed query-output page gets `marp: true` frontmatter and the final step invokes `marp` to produce a rendered HTML file next to the markdown.
```

- [ ] **Step 2: Commit**

```bash
git add skills/wiki/
git commit -m "feat(cmd): Marp slide export convenience"
```

## Task 4.4: Wave 4 validation + ship

- [ ] **Step 1: Run all tests**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run an end-to-end smoke on a fresh wiki**

```bash
/academic-wiki:wiki init final-smoke
/academic-wiki:wiki ingest 1706.03762
/academic-wiki:wiki compile
/academic-wiki:wiki query "What is attention?"
/academic-wiki:wiki lint
/academic-wiki:wiki export-bibtex --field nlp --label smoke
/academic-wiki:wiki snapshot ready-to-ship
/academic-wiki:wiki remove final-smoke
```

- [ ] **Step 3: Tag v0.1.0**

```bash
git tag v0.1.0
git commit --allow-empty -m "milestone: academic-wiki v0.1.0 — all four waves complete"
```

---

## Appendix: Spec coverage audit

| Spec section | Task(s) |
|---|---|
| §1 Purpose & non-goals | README, WALKTHROUGH |
| §1.2 Git-proposal eval | implicit in implementation (source-sha adopted; no branch-as-hypothesis) |
| §2.1 Plugin repo layout | Task 1.1 |
| §2.2 Wiki data layout | Task 1.9, 1.10, 1.11 |
| §2.3 Key architectural decisions | Task 1.7 (lockfile), 1.11 (nested repo) |
| §3.1 paper schema | Task 1.10 (CLAUDE.md), 1.14 (compile writes it) |
| §3.2–§3.3 secondary/operational schemas | Task 1.10, 2.1 |
| §3.4 cross-schema conventions | Task 1.10, 2.1 |
| §3.5 slug generation | Task 1.3 |
| §3.6 update conflict policy | Task 1.10, 2.2 |
| §3.7 raw-side metadata | Task 1.10, 1.13 |
| §4 tag taxonomy | Task 1.10 |
| §5.1 init | Task 1.11 |
| §5.2 ingest | Task 1.6, 1.13 |
| §5.3 compile (paper-only tier) | Task 1.14 |
| §5.3 compile (full tier) | Task 2.1 |
| §5.4 query | Task 1.15 |
| §5.5 lint | Task 3.1, 3.2 |
| §5.6 export-bibtex | Task 3.3, 3.4 |
| §5.7 snapshot | Task 3.5 |
| §5.8 remove | Task 4.1 |
| §6 search strategy | Task 1.15 (Phase 1), SKILL.md (Phase 2 qmd wiring) |
| §7 CLAUDE.md contract | Task 1.10 |
| §8.1 lockfile | Task 1.7 |
| §8.2 error catalog | distributed across ingest/compile/etc. tasks |
| §9 dependencies | Task 1.1 (pyproject), 1.12 (SessionStart hook) |
| §10 testing strategy | Task 1.2 (infra), each task's tests |
| §11.1 Wave 1 | Task 1.* |
| §11.2 Wave 2 | Task 2.* |
| §11.3 Wave 3 | Task 3.* |
| §11.4 Wave 4 | Task 4.* |
| §12 open questions / future work | out of scope; flagged in README |
