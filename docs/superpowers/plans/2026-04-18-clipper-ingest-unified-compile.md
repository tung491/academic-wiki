# Clipper Ingest & Unified Compile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support Obsidian Web Clipper directories as ingest sources (in-place enrichment), unify paper-id format (no hyphens), and merge compile waves into a single pipeline.

**Architecture:** Three changes applied bottom-up: (1) paper_id.py format change + collision suffix, (2) wiki_paths.py gains `find_all_extracts()`, (3) skill/reference docs updated for clipper routing + unified compile. Tests updated alongside each code change. Wiki will be deleted and re-initialized after all changes land.

**Tech Stack:** Python 3 (academic_wiki_lib), pytest, Markdown skill files

**Spec:** `docs/superpowers/specs/2026-04-18-clipper-ingest-unified-compile-design.md`

---

### Task 1: Update `generate_paper_id()` — drop hyphens

**Files:**
- Modify: `scripts/academic_wiki_lib/paper_id.py:51-57`
- Test: `tests/test_paper_id.py`

- [ ] **Step 1: Update existing tests to expect new format**

In `tests/test_paper_id.py`, update all `generate_paper_id` test assertions from hyphenated to non-hyphenated format:

```python
def test_basic_paper_id():
    assert generate_paper_id("Vaswani", 2017, "Attention Is All You Need") == "vaswani2017attention"

def test_stop_word_in_title_dropped():
    assert generate_paper_id("Smith", 2020, "The Future of AI") == "smith2020future"

def test_ascii_fold_in_lastname():
    assert generate_paper_id("García", 2024, "Survey of RSMA") == "garcia2024survey"

def test_pure_numeric_first_word_skipped():
    assert generate_paper_id("Chen", 2023, "1000 Genomes Project") == "chen2023genomes"

def test_alphanumeric_first_word_kept():
    assert generate_paper_id("Chen", 2023, "5G Networks") == "chen20235g"
    assert generate_paper_id("Smith", 2024, "3D Printing Trends") == "smith20243d"

def test_multiple_stop_words_skipped():
    assert generate_paper_id("Jones", 2022, "A the of Framework for Deep Learning") == "jones2022framework"

def test_hyphenated_lastname():
    assert generate_paper_id("García-Luna", 2024, "Foo Bar") == "garcialuna2024foo"

def test_empty_lastname_fallback():
    result = generate_paper_id("---", 2024, "Title Here")
    assert result == "unknown2024title"

def test_empty_title_fallback():
    result = generate_paper_id("Smith", 2024, "A the of")
    assert result == "smith2024untitled"

def test_ascii_fold_nordic_germanic_letters():
    assert generate_paper_id("Øster", 2024, "Foo Bar") == "oster2024foo"
    assert generate_paper_id("Müller", 2024, "Baz") == "muller2024baz"
    assert generate_paper_id("Straße", 2024, "Test") == "strasse2024test"
    assert generate_paper_id("Æther", 2024, "Qux") == "aether2024qux"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_paper_id.py -k "test_basic_paper_id or test_stop_word or test_ascii_fold_in_lastname or test_hyphenated_lastname or test_empty_title or test_ascii_fold_nordic" -v`
Expected: FAIL — old format still returns hyphens.

- [ ] **Step 3: Update `generate_paper_id()` implementation**

In `scripts/academic_wiki_lib/paper_id.py`, change line 52 and 57:

```python
def generate_paper_id(lastname: str, year: int, title: str) -> str:
    """Generate a paper-id: <lastname><year><firstword> (no separators)."""
    ln = re.sub(r"[^a-z0-9]", "", _ascii_fold(lastname))
    if not ln:
        ln = "unknown"
    fw = _first_meaningful_word(title)
    return f"{ln}{year}{fw}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_paper_id.py -v`
Expected: All `generate_paper_id` tests PASS. Some `resolve_collision` tests will FAIL (they still use hyphenated ids) — that's expected, fixed in Task 2.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/paper_id.py tests/test_paper_id.py
git commit -m "feat: paper-id format drops hyphens (vaswani2017attention)"
```

---

### Task 2: Update `resolve_collision()` — suffix without separator + clipper scan

**Files:**
- Modify: `scripts/academic_wiki_lib/paper_id.py:118-126`
- Test: `tests/test_paper_id.py`

- [ ] **Step 1: Update collision tests to expect new format**

In `tests/test_paper_id.py`, update collision test assertions and fixtures:

```python
def test_resolve_collision_appends_numeric_suffix(tmp_wiki):
    (tmp_wiki / "wiki/papers/smith2020neural.md").write_text("---\n---\n")
    result = resolve_collision(str(tmp_wiki), "smith2020neural")
    assert result == "smith2020neural2"

def test_resolve_collision_finds_next_available(tmp_wiki):
    (tmp_wiki / "wiki/papers/smith2020neural.md").write_text("")
    (tmp_wiki / "wiki/papers/smith2020neural2.md").write_text("")
    (tmp_wiki / "wiki/papers/smith2020neural3.md").write_text("")
    result = resolve_collision(str(tmp_wiki), "smith2020neural")
    assert result == "smith2020neural4"

def test_resolve_collision_no_collision(tmp_wiki):
    result = resolve_collision(str(tmp_wiki), "brandnew2025paper")
    assert result == "brandnew2025paper"
```

- [ ] **Step 2: Add test for clipper frontmatter collision**

```python
def test_resolve_collision_checks_clipper_frontmatter(tmp_wiki):
    """resolve_collision must also check paper-id values in clipper .md frontmatter."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    clipper_dir = tmp_wiki / "raw/papers/Some_Paper_Dir"
    clipper_dir.mkdir(parents=True)
    clipper_md = clipper_dir / "Some_Paper.md"
    write_frontmatter(str(clipper_md), {"paper-id": "smith2020neural"}, "body")
    # No wiki/papers/smith2020neural.md exists, but the clipper has claimed it
    result = resolve_collision(str(tmp_wiki), "smith2020neural")
    assert result == "smith2020neural2"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_paper_id.py -k "resolve_collision" -v`
Expected: FAIL — old code still uses `-N` suffix and doesn't scan clipper dirs.

- [ ] **Step 4: Update `resolve_collision()` implementation**

In `scripts/academic_wiki_lib/paper_id.py`:

```python
def resolve_collision(wiki_root, proposed_id: str) -> str:
    """If proposed_id is taken (wiki/papers/ or clipper frontmatter), append 2, 3, ..."""
    papers_dir = Path(wiki_root) / "wiki" / "papers"
    raw_papers_dir = Path(wiki_root) / "raw" / "papers"

    def _is_taken(candidate: str) -> bool:
        if (papers_dir / f"{candidate}.md").exists():
            return True
        if raw_papers_dir.is_dir():
            for d in raw_papers_dir.iterdir():
                if not d.is_dir():
                    continue
                for md in d.glob("*.md"):
                    try:
                        fm, _ = read_frontmatter(str(md))
                        if fm.get("paper-id") == candidate:
                            return True
                    except Exception:
                        continue
        return False

    candidate = proposed_id
    suffix = 2
    while _is_taken(candidate):
        candidate = f"{proposed_id}{suffix}"
        suffix += 1
    return candidate
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_paper_id.py -v`
Expected: ALL tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/academic_wiki_lib/paper_id.py tests/test_paper_id.py
git commit -m "feat: resolve_collision uses suffix without separator, scans clipper dirs"
```

---

### Task 3: Add `find_all_extracts()` to `wiki_paths.py`

**Files:**
- Modify: `scripts/academic_wiki_lib/wiki_paths.py`
- Test: `tests/test_wiki_paths.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_wiki_paths.py`:

```python
from academic_wiki_lib.wiki_paths import find_all_extracts

def test_find_all_extracts_from_raw_extracts(tmp_wiki):
    """Finds standard extracts in raw/extracts/."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    extract = tmp_wiki / "raw/extracts/vaswani2017attention.md"
    write_frontmatter(str(extract), {"paper-id": "vaswani2017attention"}, "body")
    result = find_all_extracts(str(tmp_wiki))
    assert result == [("vaswani2017attention", str(extract))]

def test_find_all_extracts_from_clipper_dirs(tmp_wiki):
    """Finds clipper .md files in raw/papers/*/."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    clipper_dir = tmp_wiki / "raw/papers/Some_Paper_Dir"
    clipper_dir.mkdir(parents=True)
    clipper_md = clipper_dir / "Some_Paper.md"
    write_frontmatter(str(clipper_md), {"paper-id": "smith2020survey"}, "body")
    result = find_all_extracts(str(tmp_wiki))
    assert result == [("smith2020survey", str(clipper_md))]

def test_find_all_extracts_both_sources(tmp_wiki):
    """Merges both raw/extracts/ and raw/papers/*/ sources, sorted by paper-id."""
    from academic_wiki_lib.frontmatter import write_frontmatter
    # Standard extract
    e1 = tmp_wiki / "raw/extracts/vaswani2017attention.md"
    write_frontmatter(str(e1), {"paper-id": "vaswani2017attention"}, "body")
    # Clipper extract
    clipper_dir = tmp_wiki / "raw/papers/Some_Dir"
    clipper_dir.mkdir(parents=True)
    e2 = clipper_dir / "Paper.md"
    write_frontmatter(str(e2), {"paper-id": "chen2023wireless"}, "body")
    result = find_all_extracts(str(tmp_wiki))
    assert len(result) == 2
    assert result[0][0] == "chen2023wireless"  # sorted alphabetically
    assert result[1][0] == "vaswani2017attention"

def test_find_all_extracts_skips_no_paper_id(tmp_wiki):
    """Clipper .md without paper-id in frontmatter is skipped (not yet ingested)."""
    clipper_dir = tmp_wiki / "raw/papers/Unprocessed_Dir"
    clipper_dir.mkdir(parents=True)
    (clipper_dir / "Paper.md").write_text("---\ntitle: Something\n---\nbody")
    result = find_all_extracts(str(tmp_wiki))
    assert result == []

def test_find_all_extracts_skips_versions_yml(tmp_wiki):
    """*.versions.yml files in raw/extracts/ must not be treated as extracts."""
    (tmp_wiki / "raw/extracts/paper.versions.yml").write_text("- version: v1\n")
    result = find_all_extracts(str(tmp_wiki))
    assert result == []

def test_find_all_extracts_empty_wiki(tmp_wiki):
    """Empty wiki returns empty list."""
    result = find_all_extracts(str(tmp_wiki))
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_wiki_paths.py -k "find_all_extracts" -v`
Expected: FAIL — `find_all_extracts` doesn't exist yet.

- [ ] **Step 3: Implement `find_all_extracts()`**

Add `from academic_wiki_lib.frontmatter import read_frontmatter` to the **module-level imports** at the top of `scripts/academic_wiki_lib/wiki_paths.py` (next to the existing `from pathlib import Path`). Then add the function:

```python
def find_all_extracts(wiki_root) -> list[tuple[str, str]]:
    """Find all ingested extracts from both standard and clipper sources.

    Scans:
      - raw/extracts/*.md (standard ingest)
      - raw/papers/*/<file>.md (clipper ingest, must have paper-id in frontmatter)

    Returns sorted list of (paper_id, md_path) tuples, alphabetical by paper_id.
    """
    basep = Path(os.fspath(wiki_root))
    results: list[tuple[str, str]] = []

    extracts_dir = basep / "raw" / "extracts"
    if extracts_dir.is_dir():
        for md in extracts_dir.glob("*.md"):
            try:
                fm, _ = read_frontmatter(str(md))
                pid = fm.get("paper-id")
                if pid:
                    results.append((pid, str(md)))
            except Exception:
                continue

    raw_papers_dir = basep / "raw" / "papers"
    if raw_papers_dir.is_dir():
        for d in raw_papers_dir.iterdir():
            if not d.is_dir():
                continue
            for md in d.glob("*.md"):
                try:
                    fm, _ = read_frontmatter(str(md))
                    pid = fm.get("paper-id")
                    if pid:
                        results.append((pid, str(md)))
                except Exception:
                    continue

    results.sort(key=lambda t: t[0])
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_wiki_paths.py -v`
Expected: ALL tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/wiki_paths.py tests/test_wiki_paths.py
git commit -m "feat: add find_all_extracts() scanning extracts + clipper dirs"
```

---

### Task 4: Update `templates.py` — drop `citation-key`, new paper-id format

**Files:**
- Modify: `scripts/academic_wiki_lib/templates.py:69-674`
- Test: `tests/test_templates.py`

- [ ] **Step 1: Update test assertions**

In `tests/test_templates.py`, update `test_claude_md_contains_key_spec_content`:

```python
def test_claude_md_contains_key_spec_content():
    """Spot checks that specific content from key spec sections is present."""
    doc = claude_md("academic")
    assert "paper-id" in doc
    assert "citation-key" not in doc  # CHANGED: citation-key dropped
    assert "identifiers:" in doc
    assert "NFKD" in doc
    assert "source-sha" in doc
    assert "field/" in doc
    assert "subfield/" in doc
    assert "arXiv" in doc
    assert "snapshot/" in doc
    assert ".lock" in doc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_templates.py::test_claude_md_contains_key_spec_content -v`
Expected: FAIL — `citation-key` still present in template.

- [ ] **Step 3: Update `_CLAUDE_MD_SKELETON` in `templates.py`**

Apply the following changes to the `_CLAUDE_MD_SKELETON` string in `templates.py`:

1. **Identity Model section (~line 109-161):** Remove `citation-key` line from paper schema YAML, update `paper-id` example from `vaswani-2017-attention` to `vaswani2017attention`, update all file path examples (`bib-file`, `extract`, `notes`, `figures`) to use non-hyphenated format, update `cites:` examples to non-hyphenated format, remove the notes about citation-key vs paper-id distinction (lines 155-158).

2. **Entity type examples:** Update all `sources: [vaswani-2017-attention, ...]` to `sources: [vaswani2017attention, ...]` throughout the entity schemas.

3. **Ingest Rules section (~line 448-489):** Update step 7 paper-id format from `<lastname>-<year>-<firstword>` to `<lastname><year><firstword>`, collision suffix from `-2, -3` to `2, 3`. Update step 9 fallback to `unknown<YYYY><filenameslug>`. Update step 12 to say BibTeX `@key` uses `paper-id` (remove `citation-key` reference).

4. **Compile Rules section (~line 491-523):** Remove Wave 1/Wave 2 terminology. Describe a single compile pipeline: default is full (paper pages + entity extraction + cites resolution + backlink audit + cross-paper detection + index rebuild). `--paper-only` flag skips entity extraction through cross-paper detection.

5. **Error Catalog (~line 663):** Update collision suffix from `-2, -3` to `2, 3`.

6. **Cross-Schema Conventions section (~line 311-319):** Remove references to `citation-key` being presentation-only (item 2). Update to say references are by `paper-id`.

7. **Raw-Side Metadata Schema (~line 359-378):** Update example `paper-id` and file paths to non-hyphenated format.

- [ ] **Step 4: Run all template tests**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_templates.py -v`
Expected: ALL tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/templates.py tests/test_templates.py
git commit -m "feat: templates drop citation-key, use non-hyphenated paper-id, unified compile"
```

---

### Task 5: Update `conftest.py` fixtures to new paper-id format

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update `sample_paper_content` fixture**

```python
@pytest.fixture
def sample_paper_content():
    """A tiny paper extract for ingest/compile tests."""
    return """---
paper-id: vaswani2017attention
source-path: raw/papers/vaswani2017attention.pdf
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

- [ ] **Step 2: Run full test suite**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/ -v`
Expected: ALL tests PASS. This validates that the fixture change doesn't break anything.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "chore: update test fixtures to non-hyphenated paper-id format"
```

---

### Task 6: Update `tests/test_paper_id.py` dedup fixtures to new format

**Files:**
- Modify: `tests/test_paper_id.py`

- [ ] **Step 1: Update dedup test fixtures**

Update all tests that create paper files with hyphenated paper-ids in their frontmatter/filenames:

```python
def test_find_existing_paper_by_doi(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/vaswani2017attention.md"
    write_frontmatter(str(paper), {
        "paper-id": "vaswani2017attention",
        "identifiers": {"doi": "10.xx/yy", "arxiv": "1706.03762"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.xx/yy"})
    assert found == "vaswani2017attention"

def test_find_existing_paper_by_arxiv_different_version(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/vaswani2017attention.md"
    write_frontmatter(str(paper), {
        "paper-id": "vaswani2017attention",
        "identifiers": {"arxiv": "1706.03762", "arxiv-version": "v3"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"arxiv": "1706.03762v5"})
    assert found == "vaswani2017attention"

def test_find_existing_paper_by_arxiv_no_version_both_sides(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/x2024y.md"
    write_frontmatter(str(paper), {
        "paper-id": "x2024y",
        "identifiers": {"arxiv": "2401.12345"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"arxiv": "2401.12345"})
    assert found == "x2024y"

def test_find_existing_paper_doi_case_insensitive(tmp_wiki):
    from academic_wiki_lib.frontmatter import write_frontmatter
    paper = tmp_wiki / "wiki/papers/x2024y.md"
    write_frontmatter(str(paper), {
        "paper-id": "x2024y",
        "identifiers": {"doi": "10.1145/AbCdEf"},
    }, "")
    found = find_existing_paper_by_identifiers(str(tmp_wiki), {"doi": "10.1145/abcdef"})
    assert found == "x2024y"
```

- [ ] **Step 2: Run all paper_id tests**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_paper_id.py -v`
Expected: ALL PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_paper_id.py
git commit -m "chore: update dedup test fixtures to non-hyphenated paper-id format"
```

---

### Task 7: Update skill reference docs — `ingestion-routing.md`

**Files:**
- Modify: `skills/wiki/references/ingestion-routing.md`

- [ ] **Step 1: Add clipper directory pattern and batch scan**

Insert a new row before the "Local path ending `.md`" row in the routing table:

```markdown
| Local directory containing ≥1 `.md` + optional `images/` | Clipper handler: find `.md` inside, read frontmatter + body, extract metadata, generate paper-id, edit `.md` in place (merge frontmatter), symlink `images/` to `raw/figures/<paperid>` |
```

Add a new section after the routing table:

```markdown
## Batch scan mode

`ingest` with no path argument scans `raw/papers/*/` for directories matching the clipper pattern:

1. Walk `raw/papers/*/` looking for directories containing ≥1 `.md` file.
2. Filter to unprocessed: no `paper-id` in `.md` frontmatter, OR `paper-id` present but `extract-status` absent/not `complete` (crash recovery).
3. One `acquire()` before the loop, one `release()` after (not per-directory). EXIT trap set once.
4. Process each directory sequentially. Papers processed earlier in the batch are visible to later dedup scans.
5. Print summary: `Ingested N papers from raw/papers/`.
```

- [ ] **Step 2: Update paper-id format in post-routing pipeline**

Change step 5 from `<lastname>-<year>-<firstword>` to `<lastname><year><firstword>`. Change collision suffix from `-2, -3` to `2, 3`.

- [ ] **Step 3: Update dedup pass 1 scope**

Update step 1 of post-routing pipeline to scan both `raw/extracts/*.md` AND `raw/papers/*/` clipper `.md` files for matching `source-sha`.

- [ ] **Step 4: Commit**

```bash
git add skills/wiki/references/ingestion-routing.md
git commit -m "docs: ingestion-routing adds clipper pattern, batch scan, new paper-id format"
```

---

### Task 8: Update skill reference docs — `compilation-guide.md`

**Files:**
- Modify: `skills/wiki/references/compilation-guide.md`

- [ ] **Step 1: Rewrite to unified pipeline**

Replace the Wave 1/Wave 2 structure with a single pipeline description:

```markdown
# Compilation Guide

## Default compile (full pipeline)

Compile reads extracts and produces wiki pages. Default runs the full pipeline.
`--paper-only` skips entity extraction through cross-paper detection.

### Source discovery

Uses `find_all_extracts(wiki_root)` to scan both:
- `raw/extracts/*.md` (standard ingest)
- `raw/papers/*/` clipper directories (`.md` files with `paper-id` in frontmatter)

Returns `(paper_id, md_path)` tuples sorted by paper-id. Compile uses `md_path`
from the tuple — does NOT construct paths from paper-id.

### Per-source steps (all modes)

For each paper-id to compile:

1. Read extract `.md` via `read_frontmatter` using the `md_path` from `find_all_extracts()`.
2. Read `raw/notes/<paper-id>.md` if it exists.
3. Determine paper `status:` — `read` if user notes present and >200 chars, else `skimmed`.
4. Write (or update) `wiki/papers/<paper-id>.md` with full frontmatter and body sections.
5. Extract `references-raw: [...]` from the bibliography section.

### Additional steps (full mode only, skipped by `--paper-only`)

6. **Entity extraction:** scan extract body for concepts, methods, open-problems.
   Create/update `wiki/<type>s/<slug>.md` per entity schemas.
7. **Cites resolution:** fuzzy-match `references-raw` against existing paper pages.
   Matches populate `cites: [...]`. Unmatched stay in `references-raw:` only.
8. **Backlink audit:** grep for entity slugs with ≥2-word allowlist rule.
9. **Cross-paper candidate detection:** compare claims/results, write to
   `outputs/reports/YYYY-MM-DD-promotion-candidates.md`. Never auto-promote.

### Shared final steps (all modes)

10. **Index rebuild:** organize by `field/*` tags.
11. **Log + commit + release lock.**

### Update conflict policy

Same as before — preserve prior content, append new evidence, flag contradictions
with `[!WARNING]` callouts, never replace without provenance, bump `updated:`.
```

- [ ] **Step 2: Commit**

```bash
git add skills/wiki/references/compilation-guide.md
git commit -m "docs: compilation-guide merges waves into single pipeline"
```

---

### Task 9: Update skill reference docs — `entity-schemas.md` and `bibtex-handling.md`

**Files:**
- Modify: `skills/wiki/references/entity-schemas.md`
- Modify: `skills/wiki/references/bibtex-handling.md`

- [ ] **Step 1: Update `entity-schemas.md`**

1. Change header from "Reference for compile (full tier, Wave 2)" to "Reference for compile".
2. In the paper schema YAML: remove `citation-key` line, change `paper-id` example from `vaswani-2017-attention` to `vaswani2017attention`, update all file path examples to non-hyphenated format, update `cites:` examples.
3. In identity model notes (lines 53-59): remove the bullet about `citation-key`, update `paper-id` format description to `<lastname><year><firstword>`.
4. In cross-schema conventions (line 203): change "References are by `paper-id`, not `citation-key`" to just "All internal references use `paper-id`."
5. Update `sources:` examples in concept/method/etc schemas from `vaswani-2017-attention` to `vaswani2017attention`.

- [ ] **Step 2: Update `bibtex-handling.md`**

Replace line 19 with:
```markdown
The `@key` field inside the bib is the **paper-id** (e.g., `vaswani2017attention`). This is the same identifier used everywhere in the wiki — filenames, frontmatter, wikilinks, and BibTeX exports.
```

Remove the sentence "This is distinct from the `paper-id` (hyphenated, `vaswani-2017-attention`)."

Update the example BibTeX key from `vaswani2017attention` (already correct format, but add a note that it matches paper-id).

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/references/entity-schemas.md skills/wiki/references/bibtex-handling.md
git commit -m "docs: entity-schemas and bibtex-handling drop citation-key, use new paper-id format"
```

---

### Task 10: Update `SKILL.md` — clipper routing, unified compile, paper-id format

**Files:**
- Modify: `skills/wiki/SKILL.md`

This is the largest change. Apply all modifications to the main skill file.

- [ ] **Step 1: Update ingest section — add clipper routing**

In the `ingest` section, after step 2 (Route input), add the clipper directory handling. Before the existing "local `.md`" pattern in the routing reference, add the clipper directory pattern.

Add a new subsection before the existing steps:

```markdown
### Batch scan mode (no arguments)

When `ingest` is called with no path argument:

1. Walk `raw/papers/*/` for directories containing ≥1 `.md` file.
2. Filter: no `paper-id` in frontmatter, OR `paper-id` present but `extract-status` absent/not `complete`.
3. Acquire lock once before the loop; release after all directories processed.
4. Process each sequentially (dedup sees earlier papers in same batch).
5. Print: `Ingested N papers from raw/papers/`.

### Clipper directory ingest

When a directory is detected (batch scan or explicit path):

1. Find the `.md` file inside.
2. Read frontmatter + body, extract metadata.
3. Generate paper-id (standard pipeline).
4. Dedup: scan both `raw/extracts/*.md` AND `raw/papers/*/` clipper `.md` for source-sha; scan `wiki/papers/*.md` for identifiers.
5. Edit `.md` in place: `read_frontmatter()`, merge missing fields, `write_frontmatter()`. Inject: `paper-id`, `source-sha`, `source-type: clipper-md`, `source-url`, `extracted-at`, `extract-status: complete`, `extractor: obsidian-clipper`, `ocr-used: false`, `extract-warnings: []`.
6. If `images/` exists: `ln -sr raw/papers/<dir>/images raw/figures/<paperid>` (relative symlink).
7. Stub BibTeX to `raw/bib/<paperid>.bib`.
8. Log + commit.
```

- [ ] **Step 2: Update ingest step 4 — dedup pass 1 scope**

Patch the existing ingest step 4 (byte-level dedup) in SKILL.md to scan BOTH `raw/extracts/*.md` AND `raw/papers/*/` clipper `.md` files for matching `source-sha` in frontmatter. The current text says "scan existing `raw/extracts/*.md`" — expand this to include clipper sources so non-clipper ingests also detect duplicates against previously ingested clipper papers.

- [ ] **Step 3: Update paper-id format references**

Throughout `SKILL.md`:
- Step 7: change `<lastname>-<year>-<firstword>` to `<lastname><year><firstword>`, collision suffix `2, 3` not `-2, -3`.
- Step 9: fallback to `unknown<currentyear><filenameslug>`.
- Step 12: change "BibTeX `@key` uses `citation-key`" to "BibTeX `@key` uses `paper-id`".

- [ ] **Step 4: Update compile section — remove Wave terminology**

Replace the Wave 1/Wave 2 structure with the unified pipeline:
- Default compile = full pipeline (paper pages + entity extraction + cites + backlinks + cross-paper + index).
- `--paper-only` = paper pages + index + log/commit only.
- Remove all "Wave 1", "Wave 2" references.

- [ ] **Step 5: Update compile to use `find_all_extracts()` and `md_path`**

Two changes in the compile section:
1. **Step 2 (Identify sources):** change from scanning only `raw/extracts/*.md` to using `find_all_extracts()` which returns `(paper_id, md_path)` tuples from both `raw/extracts/` and `raw/papers/*/`.
2. **Step 3a (Per-source read):** change `Read raw/extracts/<paper-id>.md` to read the `md_path` from the `find_all_extracts()` tuple. Do NOT construct a path from `paper-id` — the path formula differs per source type (standard extracts vs clipper dirs).

Also update the Error Catalog entry for "compile targets non-existent paper-id" to say `No extract found for <paper-id>` instead of referencing `raw/extracts/<paper-id>.md` specifically.

- [ ] **Step 6: Commit**

```bash
git add skills/wiki/SKILL.md
git commit -m "feat: SKILL.md adds clipper routing, unified compile, new paper-id format"
```

---

### Task 11: Run full test suite and verify

**Files:**
- All test files

- [ ] **Step 1: Run full test suite**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/ -v`
Expected: ALL tests PASS.

- [ ] **Step 2: Verify no stale references**

Run: `cd /home/tung491/Work/academic_wiki && grep -rn "citation-key" skills/ scripts/academic_wiki_lib/ tests/`
Expected: No matches (citation-key fully removed from code, skill docs, and tests).

Run: `cd /home/tung491/Work/academic_wiki && grep -rn "Wave 1\|Wave 2" skills/ scripts/academic_wiki_lib/ tests/`
Expected: No matches (wave terminology fully removed from all sources).

- [ ] **Step 3: Commit if any fixes needed**

```bash
git add -A && git commit -m "fix: clean up stale references"
```
