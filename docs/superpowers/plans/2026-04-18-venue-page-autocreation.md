# Venue Page Auto-Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/academic-wiki:wiki compile` auto-derive `venue/<slug>` + `year/<YYYY>` tags on paper pages and create/update `wiki/venues/<slug>.md` pages from the raw venue string captured by the clipper.

**Architecture:** The clipper and MCP publisher handlers already capture the raw venue string (e.g., `"IEEE Communications Surveys & Tutorials"`) in extract frontmatter. Compile currently slugifies it into the paper page's `venue:` field but (a) skips the matching `venue/*` and `year/*` tags and (b) never creates a venue page. The fix lives in the `wiki` skill's compile instructions plus two small helpers in `academic_wiki_lib.templates`: `guess_venue_type()` (heuristic → conference/journal/workshop/preprint-server) and `venue_md_stub()` (renders the §3 schema). The CLAUDE.md schema description is updated to state venue pages are auto-created. Finally, the five existing paper pages in the live `academic` wiki are backfilled and the shared venue page is created by hand so the wiki reaches the correct post-fix state without a forced recompile.

**Tech Stack:** Python 3 (helpers + tests), pytest, PyYAML via `academic_wiki_lib.frontmatter`, markdown (skill docs).

---

### Task 1: `guess_venue_type()` helper

**Files:**
- Modify: `scripts/academic_wiki_lib/templates.py` (append new function)
- Test: `tests/test_templates.py` (append new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_templates.py`:

```python
from academic_wiki_lib.templates import guess_venue_type


def test_guess_venue_type_journal_keywords():
    assert guess_venue_type("IEEE Transactions on Networking") == "journal"
    assert guess_venue_type("IEEE Communications Surveys & Tutorials") == "journal"
    assert guess_venue_type("Nature Machine Intelligence") == "journal"
    assert guess_venue_type("Computer Networks") == "journal"
    assert guess_venue_type("IEEE Communications Letters") == "journal"


def test_guess_venue_type_conference_keywords():
    assert guess_venue_type("IEEE International Conference on Communications") == "conference"
    assert guess_venue_type("ACM Symposium on Theory of Computing") == "conference"
    assert guess_venue_type("Proceedings of NeurIPS 2024") == "conference"


def test_guess_venue_type_workshop():
    assert guess_venue_type("NeurIPS 2024 Workshop on Foundation Models") == "workshop"


def test_guess_venue_type_preprint_server():
    assert guess_venue_type("arXiv") == "preprint-server"
    assert guess_venue_type("arXiv preprint") == "preprint-server"
    assert guess_venue_type("bioRxiv") == "preprint-server"


def test_guess_venue_type_default_is_journal():
    assert guess_venue_type("Unknown Publication") == "journal"


def test_guess_venue_type_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        guess_venue_type("")
    with pytest.raises(ValueError):
        guess_venue_type("   ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && ~/.venv/bin/python -m pytest tests/test_templates.py::test_guess_venue_type_journal_keywords -v`
Expected: `ImportError: cannot import name 'guess_venue_type'`

- [ ] **Step 3: Implement `guess_venue_type`**

Append to `scripts/academic_wiki_lib/templates.py`:

```python
_WORKSHOP_RE = __import__("re").compile(r"\bworkshop\b", __import__("re").IGNORECASE)
_CONFERENCE_RE = __import__("re").compile(
    r"\b(conference|symposium|proceedings|workshop on|congress)\b",
    __import__("re").IGNORECASE,
)
_JOURNAL_RE = __import__("re").compile(
    r"\b(transactions|journal|letters|surveys|magazine|tutorials|nature|science|communications|review|cell|lancet|jama|"
    r"physical review|acta|annals|bulletin)\b",
    __import__("re").IGNORECASE,
)
_PREPRINT_RE = __import__("re").compile(r"\b(arxiv|biorxiv|medrxiv|chemrxiv|ssrn|preprint server)\b", __import__("re").IGNORECASE)


def guess_venue_type(raw_venue: str) -> str:
    """Heuristic classification of a raw venue string.

    Returns one of: "conference", "journal", "workshop", "preprint-server".
    Defaults to "journal" when no keyword matches — journals are the most common
    academic venue and are cheap to correct by hand when wrong.
    """
    if not raw_venue or not raw_venue.strip():
        raise ValueError("Cannot classify empty venue string")

    # workshop must win over conference (a venue can contain both words)
    if _WORKSHOP_RE.search(raw_venue):
        return "workshop"
    if _PREPRINT_RE.search(raw_venue):
        return "preprint-server"
    if _CONFERENCE_RE.search(raw_venue):
        return "conference"
    if _JOURNAL_RE.search(raw_venue):
        return "journal"
    return "journal"
```

Use plain `import re` at the top of the file instead of the `__import__` shim if `re` is not already imported there — check the file; `templates.py` currently has no `import re`, so add `import re` to the imports block at the top and drop the `__import__` calls.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && ~/.venv/bin/python -m pytest tests/test_templates.py -k guess_venue_type -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/templates.py tests/test_templates.py
git commit -m "feat: add guess_venue_type heuristic for venue classification"
```

---

### Task 2: `venue_md_stub()` template

**Files:**
- Modify: `scripts/academic_wiki_lib/templates.py`
- Test: `tests/test_templates.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_templates.py`:

```python
from academic_wiki_lib.templates import venue_md_stub


def test_venue_md_stub_has_all_required_fields():
    md = venue_md_stub(
        slug="ieee-communications-surveys-tutorials",
        name="IEEE Communications Surveys & Tutorials",
        venue_type="journal",
        paper_ids=["gao2026agentic"],
        field_tags=["field/wireless-communications"],
        today="2026-04-18",
    )
    assert "type: venue" in md
    assert "name: \"IEEE Communications Surveys & Tutorials\"" in md
    assert "slug: ieee-communications-surveys-tutorials" in md
    assert "venue-type: journal" in md
    assert "created: 2026-04-18" in md
    assert "updated: 2026-04-18" in md
    assert "- gao2026agentic" in md
    assert "- field/wireless-communications" in md


def test_venue_md_stub_multiple_papers_and_fields():
    md = venue_md_stub(
        slug="neurips",
        name="Conference on Neural Information Processing Systems",
        venue_type="conference",
        paper_ids=["vaswani2017attention", "bahdanau2014neural"],
        field_tags=["field/nlp", "field/ml"],
        today="2026-04-18",
    )
    assert "- vaswani2017attention" in md
    assert "- bahdanau2014neural" in md
    assert "- field/nlp" in md
    assert "- field/ml" in md


def test_venue_md_stub_body_has_section_headers():
    md = venue_md_stub(
        slug="x", name="X", venue_type="journal",
        paper_ids=["a2024b"], field_tags=["field/x"], today="2026-04-18",
    )
    # Body is minimal: an auto-populated "Papers" section placeholder is fine;
    # the Papers list itself is rendered via Dataview in Obsidian, so the stub
    # body just has a one-line description.
    assert "---" in md  # frontmatter delimiters
    assert md.count("---") >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && ~/.venv/bin/python -m pytest tests/test_templates.py -k venue_md_stub -v`
Expected: `ImportError: cannot import name 'venue_md_stub'`

- [ ] **Step 3: Implement `venue_md_stub`**

Append to `scripts/academic_wiki_lib/templates.py`:

```python
def venue_md_stub(
    *,
    slug: str,
    name: str,
    venue_type: str,
    paper_ids: list[str],
    field_tags: list[str],
    today: str,
) -> str:
    """Render a minimal `wiki/venues/<slug>.md` page matching the §3 venue schema.

    Caller is responsible for dedup + sort of paper_ids and field_tags.
    """
    escaped_name = name.replace('"', '\\"')
    papers_block = "\n".join(f"  - {pid}" for pid in paper_ids) or "  []"
    tags_block = "\n".join(f"  - {t}" for t in field_tags) or "  []"
    return (
        "---\n"
        "type: venue\n"
        f"name: \"{escaped_name}\"\n"
        f"slug: {slug}\n"
        f"venue-type: {venue_type}\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        "papers:\n"
        f"{papers_block}\n"
        "tags:\n"
        f"{tags_block}\n"
        "---\n"
        "\n"
        f"# {escaped_name}\n"
        "\n"
        "Papers published in this venue are listed in the `papers:` frontmatter. "
        "Use Obsidian Dataview to render the list dynamically.\n"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && ~/.venv/bin/python -m pytest tests/test_templates.py -k venue_md_stub -v`
Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/templates.py tests/test_templates.py
git commit -m "feat: add venue_md_stub template for wiki/venues/ pages"
```

---

### Task 3: Update `SKILL.md` compile steps

**Files:**
- Modify: `skills/wiki/SKILL.md` — the `compile` section (currently around lines 302–423).

- [ ] **Step 1: Rewrite compile step 3 to be explicit about venue & tag handling**

Current `SKILL.md` step 3.f reads:
```
f. LLM infers `field/*`, `subfield/*`, `method/*` tags from content. `year/<YYYY>` and `venue/<slug>` from frontmatter.
```

Replace step 3.f and add an explicit sub-step between 3.g and 3.h so the full block reads:

```markdown
    f. LLM infers `field/*`, `subfield/*`, `method/*` tags from the extract body.
       ALWAYS add the deterministic tags from the extract frontmatter:
         - `year/<YYYY>` — from the extract's `year` or `date` field (take first 4-digit year)
         - `venue/<slug>` — where `<slug> = make_slug(<raw-venue-string>)` from the extract's `venue:` field
       Record the slug (not the raw string) in the paper page's `venue:` frontmatter field.
    g. Populate `authors:` as list of `{slug: <author-slug>, name: <human-name>}` objects. Generate each slug via `academic_wiki_lib.slug.make_slug`.
    h. Write `wiki/papers/<paper-id>.md` via `academic_wiki_lib.frontmatter.write_frontmatter`.
    i. **Venue page upsert** — after writing the paper page, create or update `wiki/venues/<venue-slug>.md`:
       - Compute `venue-type = academic_wiki_lib.templates.guess_venue_type(<raw-venue-string>)`.
       - If `wiki/venues/<venue-slug>.md` does not exist: write it via `academic_wiki_lib.templates.venue_md_stub(slug=<venue-slug>, name=<raw-venue-string>, venue_type=<venue-type>, paper_ids=[<paper-id>], field_tags=<paper's field/* tags>, today=<YYYY-MM-DD>)`.
       - If it exists: read with `read_frontmatter`, append `<paper-id>` to `papers:` (dedup), union `field/*` tags into `tags:` (dedup, preserve order), bump `updated:` to today. Do not change `created:`, `name:`, `venue-type:`, or `slug:` (user may have corrected them).
```

- [ ] **Step 2: Add a note to the top of the compile section listing venues as auto-created**

Near the `compile` heading, in the paragraph that describes what compile does (around lines 302–306), append:

```
Venue pages under `wiki/venues/<slug>.md` are auto-created or updated for every paper with a venue in its extract frontmatter.
```

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/SKILL.md
git commit -m "feat: SKILL.md compile auto-creates venue pages + year/venue tags"
```

---

### Task 4: Update `compilation-guide.md`

**Files:**
- Modify: `skills/wiki/references/compilation-guide.md`

- [ ] **Step 1: Expand step 4 and add a new step 4b**

Current step 4 (around line 24–26) describes the paper-page write. Replace it with:

```markdown
4. Write (or update) `wiki/papers/<paper-id>.md` with:
    - Full frontmatter per §3.1: `paper-id`, `type: paper`, `status`, `created` (today if new), `updated` (today), `publication-date` (if known), `title`, `authors` (list of `{slug, name}` objects), `year`, `venue` (**slug** form via `make_slug(<raw-venue>)`), `identifiers`, `aliases: []`, `source-version`, `bib-file`, `extract`, `notes` (only if `raw/notes/<paper-id>.md` exists), `figures` (only if `raw/figures/<paper-id>/` is non-empty), `references-raw` (list of raw bibliography strings), `cites: []` (empty in `--paper-only` mode; resolved in full mode), `tags`.
    - Tags MUST include the deterministic pair `year/<YYYY>` + `venue/<slug>` derived from the extract frontmatter, in addition to any LLM-inferred `field/*`, `subfield/*`, `method/*` tags.
    - Body sections: `## Metadata` (inline one-liner), `## Summary`, `## Key Contributions`, `## Methods`, `## Results`, `## Claims`, `## User Notes`, `## See Also`.

4b. **Venue page upsert** — after writing the paper page, ensure `wiki/venues/<venue-slug>.md` exists and includes this paper:
    - Compute `venue-type` via `academic_wiki_lib.templates.guess_venue_type(<raw-venue>)`.
    - New: render with `academic_wiki_lib.templates.venue_md_stub(slug=..., name=<raw-venue>, venue_type=..., paper_ids=[<paper-id>], field_tags=<paper's field/* tags>, today=<today>)`.
    - Existing: read frontmatter, append `<paper-id>` to `papers:` (dedup), union `field/*` into `tags:` (dedup), bump `updated:`. Preserve `created:`, `name:`, `venue-type:`, `slug:` (the user may have corrected them).
    - This runs in ALL modes (default AND `--paper-only`) — venue pages are cheap and belong with the paper page write.
```

- [ ] **Step 2: Commit**

```bash
git add skills/wiki/references/compilation-guide.md
git commit -m "docs: compilation-guide reflects venue page upsert"
```

---

### Task 5: Update CLAUDE.md venue schema description

**Files:**
- Modify: `scripts/academic_wiki_lib/templates.py` — the `_CLAUDE_MD_SKELETON` string.

- [ ] **Step 1: Update the section heading**

Find this block inside `_CLAUDE_MD_SKELETON` (currently around line 276):

```
### venue (secondary, on demand)
```

Replace with:

```
### venue (secondary, auto-created on compile)
```

The rest of the block (YAML schema, body description) stays the same.

- [ ] **Step 2: Add a one-liner near the Tag Taxonomy table to note the guarantee**

In the Tag Taxonomy table, the row for `venue/*` currently reads `Yes (on paper creation)`. Replace with `Yes (on compile, deterministic from extract frontmatter)`. Do the same for the `year/*` row.

- [ ] **Step 3: Run `test_claude_md_contains_key_spec_content` and confirm still passing**

Run: `cd /home/tung491/Work/academic_wiki && ~/.venv/bin/python -m pytest tests/test_templates.py::test_claude_md_contains_key_spec_content -v`
Expected: PASS. If it fails on a deleted string, adjust the test to match the new wording (the test currently only checks for `field/`, `subfield/`, `snapshot/`, etc., which aren't affected).

- [ ] **Step 4: Commit**

```bash
git add scripts/academic_wiki_lib/templates.py
git commit -m "docs: CLAUDE.md venue schema marked as auto-created"
```

---

### Task 6: Backfill the live `academic` wiki

**Files:**
- Modify: `~/Documents/Obsidian Vault/03-Resources/academic/wiki/papers/{gao2026agentic,jiang2026comprehensive,lu2026agentic,wang2025large,zhang2026toward}.md` — append `year/2025` or `year/2026` and `venue/ieee-communications-surveys-tutorials` to each paper's `tags:`.
- Create: `~/Documents/Obsidian Vault/03-Resources/academic/wiki/venues/ieee-communications-surveys-tutorials.md` — via `venue_md_stub()`.

Reasoning: compile won't re-run on these papers unless `wiki/papers/<id>.md` is stale vs the extract. Hand-patching the 5 papers + creating the shared venue page is faster than a forced recompile and avoids reopening the LLM summary flow.

- [ ] **Step 1: Read each of the 5 paper pages and append the two tags**

For each paper, the `year/*` is derived from its `year:` field (2025 or 2026) and the `venue/*` is `venue/ieee-communications-surveys-tutorials`.

Example, for `gao2026agentic.md` (year: 2026):
- Current `tags:` ends with `- method/generative-ai` (see pre-fix output).
- Append:
  ```
    - year/2026
    - venue/ieee-communications-surveys-tutorials
  ```

Repeat for:
- `gao2026agentic.md` → year/2026
- `jiang2026comprehensive.md` → year/2026
- `lu2026agentic.md` → year/2026
- `wang2025large.md` → year/2025
- `zhang2026toward.md` → year/2026

- [ ] **Step 2: Create the venue page**

```bash
PY=~/.venv/bin/python
WIKI_ROOT="$HOME/Documents/Obsidian Vault/03-Resources/academic"
PYTHONPATH="/home/tung491/Work/academic_wiki/scripts" "$PY" - <<'EOF'
from academic_wiki_lib.templates import venue_md_stub, guess_venue_type
name = "IEEE Communications Surveys & Tutorials"
slug = "ieee-communications-surveys-tutorials"
paper_ids = ["gao2026agentic", "jiang2026comprehensive", "lu2026agentic", "wang2025large", "zhang2026toward"]
# Field tags are the union across the 5 papers. Conservative minimum:
field_tags = sorted({
    "field/wireless-communications",
    "field/ai",
})
md = venue_md_stub(
    slug=slug, name=name,
    venue_type=guess_venue_type(name),
    paper_ids=sorted(paper_ids),
    field_tags=field_tags,
    today="2026-04-18",
)
import os
out = os.path.expanduser("~/Documents/Obsidian Vault/03-Resources/academic/wiki/venues/ieee-communications-surveys-tutorials.md")
with open(out, "w") as f:
    f.write(md)
print(out)
EOF
```

Verify the field-tag union by reading each paper page's `tags:` and taking the `field/*` subset. If any paper has `field/*` tags beyond `wireless-communications` and `ai`, add them to the `field_tags` list above before running.

- [ ] **Step 3: Commit inside the wiki's own repo**

```bash
WIKI_ROOT="$HOME/Documents/Obsidian Vault/03-Resources/academic"
git -C "$WIKI_ROOT" add wiki/papers wiki/venues
git -C "$WIKI_ROOT" commit -m "backfill: year/venue tags on 5 papers + venue page"
```

---

### Task 7: Run the full test suite

**Files:**
- No changes; verification step only.

- [ ] **Step 1: Run pytest**

```bash
cd /home/tung491/Work/academic_wiki && ~/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -40
```

Expected: all tests pass.

- [ ] **Step 2: If failures — diagnose & fix**

- `test_templates.py` failures in the new tests → re-check helper signatures.
- Any pre-existing test failure unrelated to this change → surface, do not silently skip.

- [ ] **Step 3: No commit needed; this is a verification step.**
