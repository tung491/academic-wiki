# Venue Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip year and ordinal from venue slugs so that different editions of the same conference series collapse to a single canonical venue page, both for new compiles and for the existing 464 venue pages in the live wiki.

**Architecture:** A deterministic Python core (`venue_normalize.py`) provides `normalize_venue(raw)` that runs paren-unwrap → ordinal-strip → year-strip → punctuation-collapse → `make_slug()` and returns `(canonical_name, slug)`. Compile-time prompts are updated to call this function instead of `make_slug` directly. A new `migrate-venues.py` CLI walks `wiki/venues/`, groups pages by their post-normalization slug, prints a dry-run plan, and on `--apply` consolidates duplicate pages (archiving merged bodies under "Merged from"), rewrites every paper page's `venue:` field and `venue/*` tag, takes a `snapshot/pre-venue-migration-<date>` git tag, and commits in one shot. A new lint check using `difflib.SequenceMatcher` flags variant-spelling near-duplicates that the deterministic rules can't catch (e.g., `ieee-cic-...` vs `ieeecic-...`).

**Tech Stack:** Python 3.10+, pytest, PyYAML via `academic_wiki_lib.frontmatter`, stdlib `difflib`, markdown (skill prompts).

**Spec:** [docs/superpowers/specs/2026-05-10-venue-normalization-design.md](../specs/2026-05-10-venue-normalization-design.md)

---

## File structure

**New:**
- `scripts/academic_wiki_lib/venue_normalize.py` — `normalize_venue()`, `near_duplicate_pairs()`
- `scripts/academic_wiki_lib/venue_migrate.py` — pure plan-building functions
- `scripts/migrate-venues.py` — CLI script (argparse + I/O + git)
- `tests/test_venue_normalize.py` — unit tests for `normalize_venue`
- `tests/test_near_duplicate.py` — unit tests for `near_duplicate_pairs`
- `tests/test_venue_migrate.py` — unit tests for `venue_migrate` pure functions
- `tests/test_migrate_venues_cli.py` — integration tests for the CLI

**Modified:**
- `scripts/lint-wiki.py` — add `_check_venue_duplicates()` and report section
- `tests/test_lint_wiki.py` — add tests for the new check
- `tests/conftest.py` — add `tmp_git_wiki` fixture (wiki tree + initialized git repo)
- `skills/wiki/references/compilation-guide.md` — Step 4b
- `skills/wiki/references/batch-compile-prompt.md` — venue slug section
- `skills/wiki/references/batch-compile-full-prompt.md` — venue slug section
- `skills/wiki/references/entity-schemas.md` — note next to venue schema

---

### Task 1: `normalize_venue()` — worked examples

**Files:**
- Create: `scripts/academic_wiki_lib/venue_normalize.py`
- Create: `tests/test_venue_normalize.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_venue_normalize.py`:

```python
"""Tests for venue normalization per spec §2026-05-10."""
import pytest

from academic_wiki_lib.venue_normalize import normalize_venue


# (raw_input, expected_canonical_name, expected_slug)
WORKED_EXAMPLES = [
    (
        "2022 56th Asilomar Conference on Signals, Systems, and Computers",
        "Asilomar Conference on Signals, Systems, and Computers",
        "asilomar-conference-on-signals-systems-and-computers",
    ),
    (
        "19th International Conference on Advanced Information Networking and Applications (AINA 2005)",
        "International Conference on Advanced Information Networking and Applications AINA",
        "international-conference-on-advanced-information-networking-and-applications-aina",
    ),
    (
        "2022 IEEE 96th Vehicular Technology Conference (VTC2022-Fall)",
        "IEEE Vehicular Technology Conference VTC-Fall",
        "ieee-vehicular-technology-conference-vtc-fall",
    ),
    (
        "2024 IEEE Globecom Workshops (GC Wkshps)",
        "IEEE Globecom Workshops GC Wkshps",
        "ieee-globecom-workshops-gc-wkshps",
    ),
    (
        "IEEE Transactions on Communications",
        "IEEE Transactions on Communications",
        "ieee-transactions-on-communications",
    ),
    (
        "arXiv preprint",
        "arXiv preprint",
        "arxiv-preprint",
    ),
]


@pytest.mark.parametrize("raw,canonical,slug", WORKED_EXAMPLES)
def test_normalize_venue_worked_examples(raw, canonical, slug):
    got_canonical, got_slug = normalize_venue(raw)
    assert got_canonical == canonical, f"canonical mismatch for {raw!r}"
    assert got_slug == slug, f"slug mismatch for {raw!r}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_normalize.py -v`
Expected: `ImportError: cannot import name 'normalize_venue'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/academic_wiki_lib/venue_normalize.py`:

```python
"""Venue normalization per spec 2026-05-10.

Strips year (1900-2099) and ordinal prefixes (Nth) from raw venue strings so
different editions of the same conference series collapse to one slug.
"""
from __future__ import annotations

import re
from typing import Iterable

from .slug import make_slug

# 4-digit year, gated by non-digit boundaries so digit-runs like "802.11" are
# left intact. Year window: 1900-2099. Update before 2100.
_YEAR_RE = re.compile(r"(?<![0-9])(?:19|20)\d{2}(?![0-9])")

# Ordinal: any positive integer followed by st/nd/rd/th (case-insensitive).
_ORDINAL_RE = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)

# Paren/bracket characters that get unwrapped to whitespace (their content is
# preserved inline so embedded acronyms like "(AINA 2005)" become "AINA 2005").
_PAREN_RE = re.compile(r"[()\[\]{}]")

# Runs of whitespace, commas, and hyphens with nothing between them collapse to
# a single space. Order matters: this runs after year/ordinal stripping leaves
# orphaned separators behind.
_DEAD_SEP_RE = re.compile(r"(?:\s|[,;])+")


def normalize_venue(raw: str) -> tuple[str, str]:
    """Return (canonical_name, slug) for a raw venue string.

    Pipeline:
      1. Unwrap parens/brackets, keeping inner text inline.
      2. Strip ordinals (1st, 2nd, 56th, ...).
      3. Strip 4-digit years (1900-2099), including glued-to-token like VTC2022.
      4. Collapse leftover whitespace/comma runs to a single space.
      5. Compute canonical_name (trimmed, original casing).
      6. Compute slug via make_slug().

    Raises ValueError when the input is empty/whitespace-only or when nothing
    remains after stripping.
    """
    if raw is None or not raw.strip():
        raise ValueError("Cannot normalize empty venue string")

    # 1. Unwrap parens/brackets
    s = _PAREN_RE.sub(" ", raw)

    # 2. Strip ordinals
    s = _ORDINAL_RE.sub(" ", s)

    # 3. Strip years (anywhere, including glued)
    s = _YEAR_RE.sub("", s)

    # 4. Collapse whitespace/comma runs. Strip leftover hyphen-only sequences
    # by also running through DEAD_SEP_RE — but keep internal hyphens that have
    # word characters on both sides.
    s = _DEAD_SEP_RE.sub(" ", s)

    # Strip stray hyphens that lost a neighbor (e.g. " - " or " -" or "- ").
    s = re.sub(r"\s+-\s+", " ", s)
    s = re.sub(r"^\s*-+\s*|\s*-+\s*$", "", s)

    canonical_name = s.strip()
    if not canonical_name:
        raise ValueError(f"Venue normalization produced empty string from: {raw!r}")

    slug = make_slug(canonical_name)
    return canonical_name, slug


def near_duplicate_pairs(
    slugs: Iterable[str],
    threshold: float = 0.92,
) -> list[tuple[str, str, float]]:
    """Stub — implemented in Task 4."""
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_normalize.py -v`
Expected: 6 PASS (one per parametrized row).

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/academic_wiki_lib/venue_normalize.py tests/test_venue_normalize.py
git commit -m "$(cat <<'EOF'
feat(venue-normalize): normalize_venue worked examples

Strip year and ordinal so editions of the same series collapse to
one slug. Worked-examples table is the contract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `normalize_venue()` — edge cases

**Files:**
- Modify: `tests/test_venue_normalize.py` (append edge-case tests)
- Modify: `scripts/academic_wiki_lib/venue_normalize.py` (patch if needed)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_venue_normalize.py`:

```python
def test_year_boundaries():
    # 1899 and 2100 are outside the 1900-2099 window — kept verbatim.
    assert normalize_venue("GLOBECOM 1899")[1] == "globecom-1899"
    assert normalize_venue("ICASSP 2100")[1] == "icassp-2100"


def test_non_year_digits_preserved():
    # 4-digit runs that aren't (19|20)NN don't match the year regex.
    # 2-3 digit runs and embedded digits like "5G", "802.11" are left alone.
    assert normalize_venue("5G NR Workshop")[1] == "5g-nr-workshop"
    assert normalize_venue("802.11 Standards Forum")[1] == "802-11-standards-forum"
    assert normalize_venue("4G LTE Forum")[1] == "4g-lte-forum"


def test_year_glued_to_token():
    assert normalize_venue("VTC2022-Fall")[1] == "vtc-fall"
    assert normalize_venue("WCNC2023")[1] == "wcnc"


def test_ordinal_anywhere():
    # Ordinals strip even when not at the start; remaining text becomes the slug.
    assert normalize_venue("21st Century Networking")[1] == "century-networking"
    assert normalize_venue("Section 1st on Optics")[1] == "section-on-optics"


def test_paren_and_bracket_unwrap():
    # All three syntaxes produce the same canonical and slug after year strip.
    a = normalize_venue("Conference on X (AINA 2005)")
    b = normalize_venue("Conference on X [AINA 2005]")
    c = normalize_venue("Conference on X AINA (2005)")
    assert a == b == c
    assert a[1] == "conference-on-x-aina"


def test_empty_input_raises():
    with pytest.raises(ValueError):
        normalize_venue("")
    with pytest.raises(ValueError):
        normalize_venue("   ")
    with pytest.raises(ValueError):
        normalize_venue(None)


def test_only_year_and_ordinal_raises():
    # Nothing left after stripping → ValueError.
    with pytest.raises(ValueError):
        normalize_venue("2024 21st")
    with pytest.raises(ValueError):
        normalize_venue("2022")


def test_trailing_leading_commas_stripped():
    canonical, slug = normalize_venue(",IEEE Transactions,")
    assert canonical == "IEEE Transactions"
    assert slug == "ieee-transactions"
```

- [ ] **Step 2: Run tests to verify they fail (or pass) as expected**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_normalize.py -v`
Expected: most pass; some may fail depending on exact regex behavior. Inspect failures.

- [ ] **Step 3: Patch implementation if any test fails**

If `test_only_year_and_ordinal_raises` fails because the function returns `("", "")` instead of raising, the existing `if not canonical_name` guard should catch it. Verify with a manual trace. If `test_paren_and_bracket_unwrap` fails for `"AINA (2005)"` (because the year is now adjacent to a paren that's been unwrapped to space), the existing pipeline already handles it — paren unwrap happens before year strip.

If anything fails, the most likely fix is in the dead-separator regex or the leftover-hyphen cleanup. Reload the function, adjust, re-run.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_normalize.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add tests/test_venue_normalize.py scripts/academic_wiki_lib/venue_normalize.py
git commit -m "$(cat <<'EOF'
test(venue-normalize): edge cases for normalize_venue

Year boundaries (1900-2099 window), non-year digits left alone,
year-glued-to-token, ordinal-anywhere, paren/bracket unwrap,
empty/only-year-and-ordinal raises ValueError.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `normalize_venue()` — idempotency property test

**Files:**
- Modify: `tests/test_venue_normalize.py`

- [ ] **Step 1: Write the property test**

Append to `tests/test_venue_normalize.py`:

```python
@pytest.mark.parametrize("raw,canonical,slug", WORKED_EXAMPLES)
def test_normalize_venue_is_idempotent(raw, canonical, slug):
    """Re-normalizing a canonical_name returns the same canonical_name and slug.

    This is the property compile relies on for re-runs to be safe: if a venue
    page already has a canonical name, compile re-normalizing it must not drift.
    """
    once_canonical, once_slug = normalize_venue(raw)
    twice_canonical, twice_slug = normalize_venue(once_canonical)
    assert once_canonical == twice_canonical
    assert once_slug == twice_slug
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_normalize.py::test_normalize_venue_is_idempotent -v`
Expected: 6 PASS (one per parametrized row). Idempotency should follow from the regex design — if it fails, that's a real bug to fix.

- [ ] **Step 3: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add tests/test_venue_normalize.py
git commit -m "$(cat <<'EOF'
test(venue-normalize): idempotency property test

Re-normalizing a canonical name returns the same name and slug.
This is what makes compile re-runs safe.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `near_duplicate_pairs()`

**Files:**
- Modify: `scripts/academic_wiki_lib/venue_normalize.py` (replace stub with implementation)
- Create: `tests/test_near_duplicate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_near_duplicate.py`:

```python
"""Tests for near_duplicate_pairs per spec 2026-05-10."""
from academic_wiki_lib.venue_normalize import near_duplicate_pairs


def test_variant_spelling_pair_flagged():
    slugs = [
        "ieee-cic-international-conference-on-communications-in-china-iccc",
        "ieeecic-international-conference-on-communications-in-china-iccc",
        "ieee-international-conference-on-communications",
    ]
    pairs = near_duplicate_pairs(slugs)
    flagged_pairs = {(a, b) for a, b, _ in pairs}
    assert (
        "ieee-cic-international-conference-on-communications-in-china-iccc",
        "ieeecic-international-conference-on-communications-in-china-iccc",
    ) in flagged_pairs


def test_distinct_conferences_not_flagged():
    slugs = [
        "ieee-international-conference-on-communications",
        "ieee-international-conference-on-image-processing",
    ]
    assert near_duplicate_pairs(slugs) == []


def test_acronym_suffix_reinforcement():
    # Two slugs that share trailing acronym `iccc` and have similarity
    # below 0.92 but ≥ 0.85 should be flagged.
    slugs = [
        "international-conference-on-communications-in-china-iccc",
        "ieee-international-conf-communications-china-iccc",
    ]
    pairs = near_duplicate_pairs(slugs)
    assert len(pairs) == 1
    a, b, _ = pairs[0]
    assert a < b
    assert a.endswith("iccc") and b.endswith("iccc")


def test_symmetry_appears_once_lex_sorted():
    slugs = ["zzz-conf", "aaa-conf"]  # both end in -conf, similarity high enough
    pairs = near_duplicate_pairs(slugs, threshold=0.5)
    # Each pair should appear once with a < b
    seen = set()
    for a, b, _ in pairs:
        assert a < b
        assert (a, b) not in seen
        seen.add((a, b))


def test_empty_and_single_input():
    assert near_duplicate_pairs([]) == []
    assert near_duplicate_pairs(["only-one"]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_near_duplicate.py -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Replace the stub with the real implementation**

In `scripts/academic_wiki_lib/venue_normalize.py`, replace the `near_duplicate_pairs` stub with:

```python
import difflib


def _slug_token_string(slug: str) -> str:
    """Convert a hyphen-slug to a space-joined token string for SequenceMatcher.

    Ratio is computed over space-separated tokens so word-level edits
    (one missing hyphen → one merged token) move the score more than
    character-level noise.
    """
    return " ".join(slug.split("-"))


def near_duplicate_pairs(
    slugs: Iterable[str],
    threshold: float = 0.92,
    acronym_threshold: float = 0.85,
) -> list[tuple[str, str, float]]:
    """Pairwise near-duplicate detection over venue slugs.

    Returns list of (slug_a, slug_b, similarity) where slug_a < slug_b
    lexicographically (no duplicates), sorted by descending similarity.

    A pair is flagged when EITHER:
      - similarity >= threshold (default 0.92), OR
      - similarity >= acronym_threshold (default 0.85) AND the slugs share
        the same trailing hyphen-token (matching acronym suffix).

    Similarity is difflib.SequenceMatcher().ratio() over the space-joined
    token form of each slug.
    """
    slug_list = sorted(set(slugs))
    out: list[tuple[str, str, float]] = []
    for i in range(len(slug_list)):
        a = slug_list[i]
        a_tokens = _slug_token_string(a)
        a_tail = a.rsplit("-", 1)[-1] if "-" in a else a
        for j in range(i + 1, len(slug_list)):
            b = slug_list[j]
            b_tokens = _slug_token_string(b)
            sim = difflib.SequenceMatcher(None, a_tokens, b_tokens).ratio()
            if sim >= threshold:
                out.append((a, b, sim))
                continue
            b_tail = b.rsplit("-", 1)[-1] if "-" in b else b
            if a_tail and a_tail == b_tail and sim >= acronym_threshold:
                out.append((a, b, sim))
    out.sort(key=lambda p: p[2], reverse=True)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_near_duplicate.py -v`
Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/academic_wiki_lib/venue_normalize.py tests/test_near_duplicate.py
git commit -m "$(cat <<'EOF'
feat(venue-normalize): near_duplicate_pairs for variant-spelling detection

difflib.SequenceMatcher over space-joined tokens, threshold 0.92.
Acronym-suffix reinforcement at 0.85 catches matching trailing
acronym pairs that fall just below the main threshold. Lex-sorted
output, no duplicate (a, b) / (b, a) pairs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Update compile-time prompts

**Files:**
- Modify: `skills/wiki/references/compilation-guide.md`
- Modify: `skills/wiki/references/batch-compile-prompt.md`
- Modify: `skills/wiki/references/batch-compile-full-prompt.md`
- Modify: `skills/wiki/references/entity-schemas.md`

No tests — these are LLM-read instructions. The unit-test contract on `normalize_venue` is what the prompts depend on.

- [ ] **Step 1: Update `compilation-guide.md` Step 4b**

Find the block in `skills/wiki/references/compilation-guide.md` that reads (search for "via `academic_wiki_lib.templates.venue_md_stub`"):

```
    - Compute `venue-type` via `academic_wiki_lib.templates.guess_venue_type(<raw-venue>)`.
    - New: render with `academic_wiki_lib.templates.venue_md_stub(slug=<venue-slug>, name=<raw-venue>, venue_type=<venue-type>, paper_ids=[<paper-id>], field_tags=<paper's field/* tags>, today=<today>)` and write the result to disk.
```

Replace with:

```
    - Compute `(canonical_name, slug)` via `academic_wiki_lib.venue_normalize.normalize_venue(<raw-venue>)`. The slug strips year/ordinal so editions collapse to one venue page.
    - Compute `venue-type` via `academic_wiki_lib.templates.guess_venue_type(<canonical_name>)`.
    - New: render with `academic_wiki_lib.templates.venue_md_stub(slug=<slug>, name=<canonical_name>, venue_type=<venue-type>, paper_ids=[<paper-id>], field_tags=<paper's field/* tags>, today=<today>)` and write the result to disk.
```

Also find the line referencing `make_slug(<raw-venue>)` for the paper page's `venue:` frontmatter (search for "make_slug(<raw-venue>)"). Replace `make_slug(<raw-venue>)` with `academic_wiki_lib.venue_normalize.normalize_venue(<raw-venue>)[1]` (the slug part of the tuple).

- [ ] **Step 2: Update `batch-compile-prompt.md`**

Find the section starting `**`venue` slug:**` (it begins with "If a venue string is present in the extract, convert it to slug form:") and replace the body of that section through the examples line with:

```
**`venue` slug:** If a venue string is present in the extract, call `academic_wiki_lib.venue_normalize.normalize_venue(<raw-venue>)` to get `(canonical_name, slug)`. Use both:
- `slug` for the `venue:` frontmatter, the `venue/<slug>` tag, and the venue page's path `wiki/venues/<slug>.md`.
- `canonical_name` for the venue page's `name:` frontmatter and the `# <heading>` line of the venue page body.

The function strips year (1900–2099) and ordinal prefixes (`1st`, `2nd`, ..., `99th`) from the raw string so different editions of the same conference series produce the same slug.

Examples:
- `"2022 56th Asilomar Conference on Signals, Systems, and Computers"` → canonical `Asilomar Conference on Signals, Systems, and Computers`, slug `asilomar-conference-on-signals-systems-and-computers`.
- `"19th International Conference on Advanced Information Networking and Applications (AINA 2005)"` → canonical `International Conference on Advanced Information Networking and Applications AINA`, slug `international-conference-on-advanced-information-networking-and-applications-aina`.
- `"IEEE Transactions on Communications"` → canonical and slug unchanged (already canonical).
```

In the same file, find any subsequent reference to `<venue-slug>` or `name: "<raw venue name from extract>"` and update them to refer to `<canonical_name>` (the human-readable form) when used for the `name:` field.

- [ ] **Step 3: Update `batch-compile-full-prompt.md`**

Apply the same edit as Step 2 to `skills/wiki/references/batch-compile-full-prompt.md` — locate the `**`venue` slug:**` section and replace it with the same content. Update any subsequent `<raw venue name from extract>` references the same way.

- [ ] **Step 4: Update `entity-schemas.md`**

Find the `**venue** — `wiki/venues/<slug>.md`` block in `skills/wiki/references/entity-schemas.md`. Just before the YAML, add a one-line note:

```
The `slug:` is produced by `academic_wiki_lib.venue_normalize.normalize_venue(<raw-venue>)`, which strips year and ordinal so editions of the same conference series collapse to one page. The `name:` is the canonical (year/ordinal-stripped) human-readable form returned by the same function.
```

- [ ] **Step 5: Manually verify the edits read coherently**

Run: `cd /home/tung491/Work/academic_wiki && grep -n "normalize_venue\|make_slug.*raw.venue" skills/wiki/references/*.md`
Expected: every venue-slug callsite calls `normalize_venue`; no leftover `make_slug(<raw-venue>)` or `make_slug(raw_venue)` strings.

- [ ] **Step 6: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add skills/wiki/references/compilation-guide.md skills/wiki/references/batch-compile-prompt.md skills/wiki/references/batch-compile-full-prompt.md skills/wiki/references/entity-schemas.md
git commit -m "$(cat <<'EOF'
docs(skill): wire normalize_venue into compile-time prompts

Compile prompts and the entity-schemas reference now point at
normalize_venue() (instead of make_slug() on the raw string).
Both outputs are used: slug for path/tag/frontmatter and
canonical_name for the human-readable venue page name.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Lint near-duplicate venue check

**Files:**
- Modify: `scripts/lint-wiki.py`
- Modify: `tests/test_lint_wiki.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lint_wiki.py`:

```python
def test_venue_near_duplicates_flagged(tmp_wiki):
    """Two venue pages with variant-spelling slugs are reported as near-duplicates."""
    from academic_wiki_lib.frontmatter import write_frontmatter

    common = {
        "type": "venue", "venue-type": "conference",
        "created": "2026-05-10", "updated": "2026-05-10",
        "papers": [], "tags": [],
    }
    write_frontmatter(
        str(tmp_wiki / "wiki/venues/ieee-cic-international-conference-on-communications-in-china-iccc.md"),
        {**common, "name": "IEEE/CIC International Conference on Communications in China",
         "slug": "ieee-cic-international-conference-on-communications-in-china-iccc"},
        "Body.\n",
    )
    write_frontmatter(
        str(tmp_wiki / "wiki/venues/ieeecic-international-conference-on-communications-in-china-iccc.md"),
        {**common, "name": "IEEECIC International Conference on Communications in China",
         "slug": "ieeecic-international-conference-on-communications-in-china-iccc"},
        "Body.\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "VENUE_NEAR_DUPLICATE" in out
    assert "ieee-cic-international-conference-on-communications-in-china-iccc" in out
    assert "ieeecic-international-conference-on-communications-in-china-iccc" in out


def test_venue_distinct_pairs_not_flagged(tmp_wiki):
    """Distinct conferences sharing common words are NOT flagged."""
    from academic_wiki_lib.frontmatter import write_frontmatter

    common = {
        "type": "venue", "venue-type": "conference",
        "created": "2026-05-10", "updated": "2026-05-10",
        "papers": [], "tags": [],
    }
    write_frontmatter(
        str(tmp_wiki / "wiki/venues/ieee-international-conference-on-communications.md"),
        {**common, "name": "IEEE International Conference on Communications",
         "slug": "ieee-international-conference-on-communications"},
        "Body.\n",
    )
    write_frontmatter(
        str(tmp_wiki / "wiki/venues/ieee-international-conference-on-image-processing.md"),
        {**common, "name": "IEEE International Conference on Image Processing",
         "slug": "ieee-international-conference-on-image-processing"},
        "Body.\n",
    )
    rc, out, _ = run_lint(tmp_wiki)
    assert "VENUE_NEAR_DUPLICATE" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_lint_wiki.py::test_venue_near_duplicates_flagged tests/test_lint_wiki.py::test_venue_distinct_pairs_not_flagged -v`
Expected: `test_venue_near_duplicates_flagged` FAILS (no `VENUE_NEAR_DUPLICATE` tag in output); `test_venue_distinct_pairs_not_flagged` passes vacuously.

- [ ] **Step 3: Implement the lint check**

In `scripts/lint-wiki.py`, near the other check functions, add:

```python
from academic_wiki_lib.venue_normalize import near_duplicate_pairs


def _check_venue_near_duplicates(files: dict[str, tuple]) -> list[str]:
    """Flag pairs of venue page slugs that look like spelling variants of each other.

    Returns a list of issue lines; empty if no pairs.
    """
    venue_slugs = []
    for slug, (path, fm, _) in files.items():
        if fm.get("type") == "venue":
            venue_slugs.append(slug)
    pairs = near_duplicate_pairs(venue_slugs)
    issues = []
    for a, b, sim in pairs:
        a_tail = a.rsplit("-", 1)[-1] if "-" in a else a
        b_tail = b.rsplit("-", 1)[-1] if "-" in b else b
        suffix_note = f"; matching acronym suffix {a_tail!r}" if a_tail == b_tail else ""
        issues.append(
            f"VENUE_NEAR_DUPLICATE: {a!r} ↔ {b!r} (similarity {sim:.2f}{suffix_note})"
        )
    return issues
```

Then find the main function in `lint-wiki.py` (search for the place where other `_check_*` functions are called and their issue strings printed) and add a call to `_check_venue_near_duplicates(files)` whose returned strings are printed alongside the other issue lines.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_lint_wiki.py::test_venue_near_duplicates_flagged tests/test_lint_wiki.py::test_venue_distinct_pairs_not_flagged -v`
Expected: both PASS.

- [ ] **Step 5: Run the full lint test file to make sure nothing else regressed**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_lint_wiki.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/lint-wiki.py tests/test_lint_wiki.py
git commit -m "$(cat <<'EOF'
feat(lint): VENUE_NEAR_DUPLICATE check

Surfaces variant-spelling venue pairs (ieee-cic vs ieeecic) that
the deterministic normalize_venue rules can't auto-merge.
Threshold 0.92 with acronym-suffix reinforcement at 0.85.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `venue_migrate.compute_plan()` — scan + grouping + conflict resolution

**Files:**
- Create: `scripts/academic_wiki_lib/venue_migrate.py`
- Create: `tests/test_venue_migrate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_venue_migrate.py`:

```python
"""Tests for venue_migrate.compute_plan — pure plan-building logic."""
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import write_frontmatter
from academic_wiki_lib.venue_migrate import compute_plan


def _venue(tmp_wiki, slug, name, papers=None, tags=None, venue_type="conference",
           created="2026-04-01"):
    fm = {
        "type": "venue",
        "name": name,
        "slug": slug,
        "venue-type": venue_type,
        "created": created,
        "updated": created,
        "papers": list(papers or []),
        "tags": list(tags or []),
    }
    write_frontmatter(str(tmp_wiki / "wiki/venues" / f"{slug}.md"), fm, "Body of " + slug + "\n")


def test_no_op_group_skipped(tmp_wiki):
    """A single canonical-slug venue is a no-op (skipped from the plan)."""
    _venue(tmp_wiki, "ieee-transactions-on-communications",
           "IEEE Transactions on Communications", papers=["p1"])
    plan = compute_plan(tmp_wiki)
    assert plan.groups == []  # no rename needed, no merge needed


def test_single_page_rename(tmp_wiki):
    """An existing non-canonical-slug venue produces a rename group."""
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["paperA"])
    plan = compute_plan(tmp_wiki)
    assert len(plan.groups) == 1
    g = plan.groups[0]
    assert g.new_slug == "asilomar-conference-on-signals-systems-and-computers"
    assert g.new_canonical_name == "Asilomar Conference on Signals, Systems, and Computers"
    assert len(g.members) == 1
    assert g.members[0].slug == "2022-56th-asilomar-conference-on-signals-systems-and-computers"
    assert g.new_papers == ["paperA"]
    assert g.is_merge is False


def test_multi_page_merge(tmp_wiki):
    """Multiple venues normalizing to the same slug form a merge group."""
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pA", "pB"], tags=["field/wireless-comms"], created="2024-01-01")
    _venue(tmp_wiki, "2023-57th-asilomar-conference-on-signals-systems-and-computers",
           "2023 57th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pC"], tags=["field/wireless-comms", "field/signal-processing"],
           created="2024-06-15")
    plan = compute_plan(tmp_wiki)
    assert len(plan.groups) == 1
    g = plan.groups[0]
    assert g.new_slug == "asilomar-conference-on-signals-systems-and-computers"
    assert g.is_merge is True
    assert len(g.members) == 2
    # Papers union, deduped, lex-sorted
    assert g.new_papers == ["pA", "pB", "pC"]
    # Tags union, deduped, lex-sorted
    assert g.new_tags == ["field/signal-processing", "field/wireless-comms"]


def test_merge_with_existing_canonical(tmp_wiki):
    """A canonical-slug page coexisting with non-canonical members is included
    as a merge member (not skipped)."""
    _venue(tmp_wiki, "asilomar-conference-on-signals-systems-and-computers",
           "Asilomar Conference on Signals, Systems, and Computers",
           papers=["pA"])
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pB"])
    plan = compute_plan(tmp_wiki)
    assert len(plan.groups) == 1
    g = plan.groups[0]
    assert g.is_merge is True
    assert len(g.members) == 2
    assert g.new_papers == ["pA", "pB"]


def test_venue_type_majority_with_paper_count_tiebreak(tmp_wiki):
    """venue-type unanimous → use it; otherwise majority; ties broken by papers count."""
    _venue(tmp_wiki, "2022-fooconf", "2022 FooConf", papers=["p1"], venue_type="conference")
    _venue(tmp_wiki, "2023-fooconf", "2023 FooConf", papers=["p2"], venue_type="conference")
    _venue(tmp_wiki, "2024-fooconf", "2024 FooConf", papers=["p3"], venue_type="journal")
    plan = compute_plan(tmp_wiki)
    g = plan.groups[0]
    assert g.new_venue_type == "conference"  # 2-vs-1 majority


def test_created_earliest_wins(tmp_wiki):
    """The merged page's created: is the earliest across members."""
    _venue(tmp_wiki, "2022-fooconf", "2022 FooConf", papers=["p1"], created="2025-01-01")
    _venue(tmp_wiki, "2023-fooconf", "2023 FooConf", papers=["p2"], created="2024-06-15")
    _venue(tmp_wiki, "2024-fooconf", "2024 FooConf", papers=["p3"], created="2024-01-10")
    plan = compute_plan(tmp_wiki)
    g = plan.groups[0]
    assert g.new_created == "2024-01-10"


def test_unparseable_frontmatter_listed_separately(tmp_wiki):
    """Pages with unparseable frontmatter are reported in plan.skipped."""
    bad = tmp_wiki / "wiki/venues/broken.md"
    bad.write_text("---\nthis: is: not: valid yaml: [\n---\nbody\n")
    plan = compute_plan(tmp_wiki)
    assert any("broken.md" in s for s in plan.skipped)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_migrate.py -v`
Expected: `ImportError: cannot import name 'compute_plan'`.

- [ ] **Step 3: Implement `compute_plan`**

Create `scripts/academic_wiki_lib/venue_migrate.py`:

```python
"""Pure plan-building functions for venue migration per spec 2026-05-10.

The CLI (scripts/migrate-venues.py) consumes these to produce the dry-run
report and to drive --apply. Keeping the logic here makes it unit-testable
without subprocess.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .frontmatter import read_frontmatter
from .venue_normalize import normalize_venue


@dataclass
class VenuePage:
    """An existing venue page on disk."""
    slug: str
    path: Path
    name: str
    venue_type: str
    created: str
    papers: list[str]
    tags: list[str]
    body: str


@dataclass
class Group:
    """A migration group: one or more existing pages that all map to new_slug."""
    new_slug: str
    new_canonical_name: str
    new_venue_type: str
    new_created: str
    members: list[VenuePage]
    new_papers: list[str]
    new_tags: list[str]

    @property
    def is_merge(self) -> bool:
        return len(self.members) > 1


@dataclass
class Plan:
    """Migration plan. groups excludes no-op groups."""
    groups: list[Group] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _scan_venue_pages(wiki_root: Path) -> tuple[list[VenuePage], list[str]]:
    """Return (parsed pages, skipped reasons)."""
    venues_dir = wiki_root / "wiki" / "venues"
    pages: list[VenuePage] = []
    skipped: list[str] = []
    if not venues_dir.is_dir():
        return pages, skipped
    for md in sorted(venues_dir.glob("*.md")):
        try:
            fm, body = read_frontmatter(md)
        except Exception as e:
            skipped.append(f"{md.name}: parse error ({e})")
            continue
        if not isinstance(fm, dict) or fm.get("type") != "venue":
            skipped.append(f"{md.name}: frontmatter type is not 'venue'")
            continue
        name = fm.get("name")
        if not isinstance(name, str) or not name.strip():
            skipped.append(f"{md.name}: missing or empty 'name:' field")
            continue
        pages.append(VenuePage(
            slug=fm.get("slug") or md.stem,
            path=md,
            name=name,
            venue_type=fm.get("venue-type", "journal"),
            created=str(fm.get("created", "")),
            papers=list(fm.get("papers") or []),
            tags=list(fm.get("tags") or []),
            body=body,
        ))
    return pages, skipped


def _resolve_venue_type(members: list[VenuePage]) -> str:
    """Most common venue-type; ties broken by member with most papers; if still
    tied, the lex-smallest old slug wins."""
    counts = Counter(m.venue_type for m in members)
    top = counts.most_common()
    if not top:
        return "journal"
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0]
    # Tie at the top.
    tied_types = [t for t, c in top if c == top[0][1]]
    # Pick the type used by the member with the most papers; tie-break by lex-smallest slug.
    candidates = [m for m in members if m.venue_type in tied_types]
    candidates.sort(key=lambda m: (-len(m.papers), m.slug))
    return candidates[0].venue_type


def _resolve_created(members: list[VenuePage]) -> str:
    valid = sorted(m.created for m in members if m.created)
    return valid[0] if valid else ""


def compute_plan(wiki_root) -> Plan:
    """Build the migration plan from the on-disk venue pages.

    Excludes no-op groups (a single page whose existing slug already equals
    its post-normalization slug).
    """
    root = Path(os.fspath(wiki_root))
    pages, skipped = _scan_venue_pages(root)

    # Group by (new_canonical_name, new_slug) computed from each page's name.
    grouped: dict[str, list[tuple[VenuePage, str]]] = {}  # new_slug -> [(page, canonical), ...]
    for page in pages:
        try:
            canonical, new_slug = normalize_venue(page.name)
        except ValueError as e:
            skipped.append(f"{page.path.name}: {e}")
            continue
        grouped.setdefault(new_slug, []).append((page, canonical))

    groups: list[Group] = []
    for new_slug, entries in sorted(grouped.items()):
        members = [e[0] for e in entries]
        # Pick the longest canonical_name as the representative human form (in
        # practice they should all be equal, but defensively prefer the most
        # descriptive variant if not).
        new_canonical_name = max((e[1] for e in entries), key=len)
        # No-op detection: single member whose existing slug already equals new_slug.
        if len(members) == 1 and members[0].slug == new_slug:
            continue
        all_papers = sorted({p for m in members for p in m.papers})
        all_tags = sorted({t for m in members for t in m.tags})
        groups.append(Group(
            new_slug=new_slug,
            new_canonical_name=new_canonical_name,
            new_venue_type=_resolve_venue_type(members),
            new_created=_resolve_created(members),
            members=members,
            new_papers=all_papers,
            new_tags=all_tags,
        ))

    return Plan(groups=groups, skipped=skipped)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_migrate.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/academic_wiki_lib/venue_migrate.py tests/test_venue_migrate.py
git commit -m "$(cat <<'EOF'
feat(venue-migrate): compute_plan with grouping + conflict resolution

Pure-function plan builder: scans wiki/venues/, groups by post-
normalization slug, picks venue-type (majority + paper-count
tie-break + lex-slug tie-break) and created (earliest), excludes
no-op groups, surfaces unparseable frontmatter as 'skipped'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `venue_migrate.collect_paper_rewrites()` — find paper pages whose `venue:` matches an old slug

**Files:**
- Modify: `scripts/academic_wiki_lib/venue_migrate.py`
- Modify: `tests/test_venue_migrate.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_venue_migrate.py`:

```python
from academic_wiki_lib.venue_migrate import collect_paper_rewrites, PaperRewrite


def _paper(tmp_wiki, slug, venue_slug, extra_tags=()):
    fm = {
        "paper-id": slug, "type": "paper", "status": "read",
        "created": "2024-01-01", "updated": "2024-01-01",
        "title": "T", "authors": [], "year": 2024,
        "venue": venue_slug,
        "identifiers": {}, "aliases": [], "bib-file": "x",
        "extract": "x", "references-raw": [], "cites": [],
        "tags": [f"venue/{venue_slug}", *extra_tags],
    }
    write_frontmatter(str(tmp_wiki / "wiki/papers" / f"{slug}.md"), fm, "Body.\n")


def test_collect_paper_rewrites_matches_venue_field_and_tag(tmp_wiki):
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    _paper(tmp_wiki, "pA",
           "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           extra_tags=["field/wireless-comms"])
    _paper(tmp_wiki, "pUnaffected", "ieee-transactions-on-communications")

    plan = compute_plan(tmp_wiki)
    rewrites = collect_paper_rewrites(tmp_wiki, plan)
    rw_by_paper = {r.paper_id: r for r in rewrites}
    assert "pA" in rw_by_paper
    assert "pUnaffected" not in rw_by_paper
    rw = rw_by_paper["pA"]
    assert rw.old_slug == "2022-56th-asilomar-conference-on-signals-systems-and-computers"
    assert rw.new_slug == "asilomar-conference-on-signals-systems-and-computers"


def test_collect_paper_rewrites_skips_papers_pointing_at_no_op_slugs(tmp_wiki):
    """If a paper's venue: equals a slug that is a no-op (already canonical),
    no rewrite is needed."""
    _venue(tmp_wiki, "ieee-transactions-on-communications",
           "IEEE Transactions on Communications", papers=["pA"])
    _paper(tmp_wiki, "pA", "ieee-transactions-on-communications")
    plan = compute_plan(tmp_wiki)
    rewrites = collect_paper_rewrites(tmp_wiki, plan)
    assert rewrites == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_migrate.py::test_collect_paper_rewrites_matches_venue_field_and_tag tests/test_venue_migrate.py::test_collect_paper_rewrites_skips_papers_pointing_at_no_op_slugs -v`
Expected: `ImportError: cannot import name 'collect_paper_rewrites'`.

- [ ] **Step 3: Implement `collect_paper_rewrites`**

Append to `scripts/academic_wiki_lib/venue_migrate.py`:

```python
@dataclass
class PaperRewrite:
    paper_id: str
    path: Path
    old_slug: str
    new_slug: str


def collect_paper_rewrites(wiki_root, plan: Plan) -> list[PaperRewrite]:
    """Find every paper page whose venue: or venue/* tag references an old
    slug that the plan will replace."""
    root = Path(os.fspath(wiki_root))

    # Build map: old_slug -> new_slug (only for slugs that actually change)
    old_to_new: dict[str, str] = {}
    for g in plan.groups:
        for m in g.members:
            if m.slug != g.new_slug:
                old_to_new[m.slug] = g.new_slug

    if not old_to_new:
        return []

    papers_dir = root / "wiki" / "papers"
    rewrites: list[PaperRewrite] = []
    if not papers_dir.is_dir():
        return rewrites
    for md in sorted(papers_dir.glob("*.md")):
        try:
            fm, _ = read_frontmatter(md)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        venue = fm.get("venue")
        tags = fm.get("tags") or []
        old_slug = None
        if isinstance(venue, str) and venue in old_to_new:
            old_slug = venue
        else:
            for t in tags:
                if isinstance(t, str) and t.startswith("venue/"):
                    candidate = t[len("venue/"):]
                    if candidate in old_to_new:
                        old_slug = candidate
                        break
        if old_slug is None:
            continue
        rewrites.append(PaperRewrite(
            paper_id=fm.get("paper-id") or md.stem,
            path=md,
            old_slug=old_slug,
            new_slug=old_to_new[old_slug],
        ))
    return rewrites
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_migrate.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/academic_wiki_lib/venue_migrate.py tests/test_venue_migrate.py
git commit -m "$(cat <<'EOF'
feat(venue-migrate): collect_paper_rewrites for venue: + venue/* tag

Walks wiki/papers/, finds every paper whose venue: or venue/* tag
references an old slug that the plan will replace. Returns
PaperRewrite records the CLI applies during --apply.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `venue_migrate.render_report()` — markdown report rendering

**Files:**
- Modify: `scripts/academic_wiki_lib/venue_migrate.py`
- Modify: `tests/test_venue_migrate.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_venue_migrate.py`:

```python
from academic_wiki_lib.venue_migrate import render_report


def test_render_report_summary_counts(tmp_wiki):
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    _venue(tmp_wiki, "2023-57th-asilomar-conference-on-signals-systems-and-computers",
           "2023 57th Asilomar Conference on Signals, Systems, and Computers", papers=["pB"])
    _venue(tmp_wiki, "2024-aina", "2024 AINA", papers=["pC"])
    _venue(tmp_wiki, "ieee-transactions-on-communications",
           "IEEE Transactions on Communications", papers=["pD"])
    _paper(tmp_wiki, "pA", "2022-56th-asilomar-conference-on-signals-systems-and-computers")
    _paper(tmp_wiki, "pB", "2023-57th-asilomar-conference-on-signals-systems-and-computers")
    _paper(tmp_wiki, "pC", "2024-aina")
    _paper(tmp_wiki, "pD", "ieee-transactions-on-communications")

    plan = compute_plan(tmp_wiki)
    rewrites = collect_paper_rewrites(tmp_wiki, plan)
    report = render_report(plan, rewrites, today="2026-05-10")

    assert "# Venue Migration Plan — 2026-05-10" in report
    assert "## Summary" in report
    assert "## Renames (single-page groups)" in report
    assert "## Merges (multi-page groups)" in report
    assert "## Paper-page rewrites" in report
    # Asilomar merge appears
    assert "asilomar-conference-on-signals-systems-and-computers" in report
    assert "merges 2 pages" in report
    # AINA rename appears (single page)
    assert "→ aina" in report
    # The IEEE Transactions venue is a no-op so does not appear
    assert "IEEE Transactions" not in report or "Transactions on Communications" not in report.split("## Skipped")[0]


def test_render_report_skipped_section(tmp_wiki):
    bad = tmp_wiki / "wiki/venues/broken.md"
    bad.write_text("---\nbroken: [\n---\nx\n")
    plan = compute_plan(tmp_wiki)
    report = render_report(plan, [], today="2026-05-10")
    assert "## Skipped (could not parse frontmatter)" in report
    assert "broken.md" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_migrate.py -v`
Expected: `ImportError: cannot import name 'render_report'`.

- [ ] **Step 3: Implement `render_report`**

Append to `scripts/academic_wiki_lib/venue_migrate.py`:

```python
def render_report(plan: Plan, rewrites: list[PaperRewrite], today: str) -> str:
    """Render the dry-run / apply report as markdown."""
    renames = [g for g in plan.groups if not g.is_merge]
    merges = [g for g in plan.groups if g.is_merge]
    n_total = sum(len(g.members) for g in plan.groups) + sum(
        1 for g in plan.groups if not g.is_merge and g.members[0].slug == g.new_slug
    )
    # Count of papers needing rewrite
    n_rewrites = len(rewrites)

    lines: list[str] = []
    lines.append(f"# Venue Migration Plan — {today}\n")
    lines.append("## Summary")
    lines.append(f"- {len(plan.groups) + len(plan.skipped)} venue pages considered "
                 f"({len(plan.skipped)} skipped, {len(plan.groups)} in plan)")
    lines.append(f"- {len(renames)} renamed (single-page groups)")
    if merges:
        merged_in = sum(len(g.members) for g in merges)
        lines.append(f"- {merged_in} pages merge into {len(merges)} canonical pages")
    lines.append(f"- {n_rewrites} paper pages need `venue:` and `venue/*` tag rewrites")
    lines.append("")

    if renames:
        lines.append("## Renames (single-page groups)")
        for g in renames:
            old = g.members[0].slug
            lines.append(f"- `{old}` → `{g.new_slug}`")
        lines.append("")

    if merges:
        lines.append("## Merges (multi-page groups)")
        for g in merges:
            lines.append(f"### `{g.new_slug}` ← merges {len(g.members)} pages")
            lines.append("Sources:")
            for m in g.members:
                lines.append(f"- `{m.slug}` ({len(m.papers)} papers)")
            lines.append(f"New `papers:` list (union, deduped, {len(g.new_papers)} entries): {g.new_papers}")
            lines.append(f"New `tags:` list (union, {len(g.new_tags)} entries): {g.new_tags}")
            lines.append(f"New `name:` \"{g.new_canonical_name}\"")
            lines.append(f"New `venue-type:` {g.new_venue_type}")
            lines.append(f"New `created:` {g.new_created}")
            lines.append("")

    if rewrites:
        lines.append("## Paper-page rewrites")
        for r in rewrites:
            lines.append(f"- `{r.paper_id}.md`: `venue: {r.old_slug}` → `{r.new_slug}`; "
                         f"tag `venue/{r.old_slug}` → `venue/{r.new_slug}`")
        lines.append("")

    if plan.skipped:
        lines.append("## Skipped (could not parse frontmatter)")
        for s in plan.skipped:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_venue_migrate.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/academic_wiki_lib/venue_migrate.py tests/test_venue_migrate.py
git commit -m "$(cat <<'EOF'
feat(venue-migrate): render_report markdown rendering

Summary, renames, merges (with member detail), paper-page rewrites,
skipped sections. Used by both --dry-run and --apply.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: `migrate-venues.py` CLI scaffold + `--dry-run`

**Files:**
- Create: `scripts/migrate-venues.py`
- Create: `tests/test_migrate_venues_cli.py`
- Modify: `tests/conftest.py` (add `tmp_git_wiki` fixture)

- [ ] **Step 1: Add the git fixture**

Append to `tests/conftest.py`:

```python
import subprocess


@pytest.fixture
def tmp_git_wiki(tmp_wiki):
    """A tmp_wiki with `git init` and an initial commit so migration tests can
    create snapshots and commits."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_wiki, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=tmp_wiki, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_wiki, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_wiki, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_wiki, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_wiki, check=True)
    return tmp_wiki
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_migrate_venues_cli.py`:

```python
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

    before = _dirhash(tmp_git_wiki)
    result = run_migrate(tmp_git_wiki, "--dry-run")
    assert result.returncode == 0, result.stderr

    # Report file written
    reports = list((tmp_git_wiki / "outputs" / "reports").glob("*-venue-migration.md"))
    assert len(reports) == 1, f"expected 1 report, got: {reports}"
    report = reports[0].read_text()
    assert "asilomar-conference-on-signals-systems-and-computers" in report
    assert "Renames" in report

    # Nothing else changed (the report file is the only new file, but dirhash includes it
    # so we instead assert that no venue or paper page changed).
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
    """If .lock is held by a live pid, both --dry-run and --apply fail."""
    import os
    # Create a lock with our own pid
    (tmp_git_wiki / ".lock").write_text(f"{os.getpid()}:2026-05-10T000000Z:other")
    result = run_migrate(tmp_git_wiki, "--dry-run")
    assert result.returncode != 0
    assert "lock" in (result.stderr + result.stdout).lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: FAIL because the script doesn't exist yet (FileNotFoundError or non-zero exit).

- [ ] **Step 4: Create the CLI scaffold**

Create `scripts/migrate-venues.py`:

```python
#!/usr/bin/env python3
"""Venue migration CLI per spec 2026-05-10.

Walks wiki/venues/, computes a normalization plan, and either prints a dry-run
report or applies the consolidation (renames + merges + paper-page rewrites).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.lockfile import LockHeld, acquire, release
from academic_wiki_lib.venue_migrate import collect_paper_rewrites, compute_plan, render_report


def _today() -> str:
    return date.today().isoformat()


def _run_dry_run(wiki_root: Path) -> tuple[int, str]:
    """Compute plan, write report. Return (exit_code, report_path)."""
    plan = compute_plan(wiki_root)
    rewrites = collect_paper_rewrites(wiki_root, plan)
    report = render_report(plan, rewrites, today=_today())
    out_path = wiki_root / "outputs" / "reports" / f"{_today()}-venue-migration.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    return 0, str(out_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Venue migration tool")
    p.add_argument("--wiki-path", required=True, type=Path)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", default=False)
    grp.add_argument("--apply", action="store_true", default=False)
    args = p.parse_args(argv)

    wiki_root = args.wiki_path.resolve()
    if not wiki_root.is_dir():
        print(f"ERROR: wiki path not found: {wiki_root}", file=sys.stderr)
        return 2

    lock_path = wiki_root / ".lock"
    op = "migrate-venues:apply" if args.apply else "migrate-venues:dry-run"
    try:
        acquire(lock_path, op)
    except LockHeld as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    try:
        if args.apply:
            print("ERROR: --apply not yet implemented (Tasks 11-15)", file=sys.stderr)
            return 4
        rc, report_path = _run_dry_run(wiki_root)
        print(f"Dry-run report written to: {report_path}")
        return rc
    finally:
        release(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
```

Make it executable:

```bash
chmod +x /home/tung491/Work/academic_wiki/scripts/migrate-venues.py
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/tung491/Work/academic_wiki
chmod +x scripts/migrate-venues.py
git add scripts/migrate-venues.py tests/test_migrate_venues_cli.py tests/conftest.py
git commit -m "$(cat <<'EOF'
feat(migrate-venues): CLI scaffold with --dry-run

argparse + lock acquire/release + plan computation + report
writing. --apply errors out with 'not yet implemented' (Tasks
11-15 follow). Tests cover dry-run report generation, default
mode, and lock-held refusal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: `--apply` for single-page renames

**Files:**
- Modify: `scripts/migrate-venues.py`
- Modify: `tests/test_migrate_venues_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_migrate_venues_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py::test_apply_single_page_rename -v`
Expected: FAIL — `--apply not yet implemented`.

- [ ] **Step 3: Implement single-page rename in `--apply`**

In `scripts/migrate-venues.py`, replace the `_run_dry_run` function and add `_run_apply` plus a helper. Update the apply branch in `main()`. The complete updated module body (replace the existing `_run_dry_run` and `main` blocks):

```python
from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter
from academic_wiki_lib.venue_migrate import (
    collect_paper_rewrites, compute_plan, render_report, Plan, PaperRewrite, Group,
)


def _today() -> str:
    return date.today().isoformat()


def _build_report(wiki_root: Path) -> tuple[Plan, list[PaperRewrite], str]:
    plan = compute_plan(wiki_root)
    rewrites = collect_paper_rewrites(wiki_root, plan)
    report = render_report(plan, rewrites, today=_today())
    return plan, rewrites, report


def _write_report(wiki_root: Path, report: str) -> Path:
    out_path = wiki_root / "outputs" / "reports" / f"{_today()}-venue-migration.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    return out_path


def _apply_rename(group: Group) -> None:
    """Rename a single-page group's file and update its slug/name/aliases."""
    page = group.members[0]
    new_path = page.path.parent / f"{group.new_slug}.md"
    fm, body = read_frontmatter(page.path)
    fm["slug"] = group.new_slug
    fm["name"] = group.new_canonical_name
    fm["updated"] = _today()
    aliases = list(fm.get("aliases") or [])
    if page.slug not in aliases:
        aliases.append(page.slug)
    fm["aliases"] = aliases
    # Move file with `git mv` to preserve history when in a git repo, else os.rename
    try:
        subprocess.run(["git", "mv", str(page.path), str(new_path)],
                       cwd=page.path.parents[2], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        # Fallback for non-git or untracked files
        page.path.rename(new_path)
    write_frontmatter(new_path, fm, body)


def _run_apply(wiki_root: Path) -> int:
    plan, rewrites, report = _build_report(wiki_root)
    _write_report(wiki_root, report)

    for g in plan.groups:
        if g.is_merge:
            # Tasks 12+ implement merges
            continue
        _apply_rename(g)
    # Tasks 13+ implement paper-page rewrites and commit
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Venue migration tool")
    p.add_argument("--wiki-path", required=True, type=Path)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", default=False)
    grp.add_argument("--apply", action="store_true", default=False)
    args = p.parse_args(argv)

    wiki_root = args.wiki_path.resolve()
    if not wiki_root.is_dir():
        print(f"ERROR: wiki path not found: {wiki_root}", file=sys.stderr)
        return 2

    lock_path = wiki_root / ".lock"
    op = "migrate-venues:apply" if args.apply else "migrate-venues:dry-run"
    try:
        acquire(lock_path, op)
    except LockHeld as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    try:
        if args.apply:
            return _run_apply(wiki_root)
        plan, rewrites, report = _build_report(wiki_root)
        out = _write_report(wiki_root, report)
        print(f"Dry-run report written to: {out}")
        return 0
    finally:
        release(lock_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: all PASS (including the dry-run tests from Task 10).

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/migrate-venues.py tests/test_migrate_venues_cli.py
git commit -m "$(cat <<'EOF'
feat(migrate-venues): --apply for single-page renames

git mv the file, update slug/name in frontmatter, push old slug
into aliases, bump updated. Body content is preserved verbatim.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: `--apply` for multi-page merges with body archival

**Files:**
- Modify: `scripts/migrate-venues.py`
- Modify: `tests/test_migrate_venues_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_migrate_venues_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py::test_apply_multi_page_merge tests/test_migrate_venues_cli.py::test_apply_merge_with_existing_canonical_preserves_body -v`
Expected: FAIL — merge logic still skips merge groups.

- [ ] **Step 3: Implement merge logic**

In `scripts/migrate-venues.py`, add helper imports and a new function. Then update `_run_apply` to call it for merge groups:

```python
from academic_wiki_lib.templates import venue_md_stub


def _apply_merge(wiki_root: Path, group: Group) -> None:
    """Merge a multi-page group into the canonical slug page.

    Writes the canonical page (overwrites if it exists), archives every
    member's body under a 'Merged from' section, deletes the source pages
    (except the canonical one if it pre-existed). All old slugs become aliases.
    """
    venues_dir = wiki_root / "wiki" / "venues"
    canon_path = venues_dir / f"{group.new_slug}.md"

    # Stub frontmatter + standard preamble body
    today = _today()
    stub = venue_md_stub(
        slug=group.new_slug,
        name=group.new_canonical_name,
        venue_type=group.new_venue_type,
        paper_ids=group.new_papers,
        field_tags=group.new_tags,
        today=today,
    )
    # Adjust created: to the earliest across members. venue_md_stub writes
    # created: today, so patch it post-hoc via frontmatter rewrite.
    stub_fm, stub_body = _split_stub(stub)
    if group.new_created:
        stub_fm["created"] = group.new_created
    # Aliases = union of all members' existing aliases + every member's old slug
    aliases: list[str] = []
    for m in group.members:
        existing_fm, _ = read_frontmatter(m.path)
        for a in existing_fm.get("aliases") or []:
            if a not in aliases:
                aliases.append(a)
        if m.slug not in aliases:
            aliases.append(m.slug)
    # Don't list the canonical slug in its own aliases.
    aliases = [a for a in aliases if a != group.new_slug]
    stub_fm["aliases"] = aliases

    # Build the body: stub preamble + Merged from section
    merged_section_lines = ["", "## Merged from", ""]
    for m in group.members:
        merged_section_lines.append(f"### `{m.slug}` — {m.name}")
        merged_section_lines.append("")
        merged_section_lines.append(m.body.rstrip())
        merged_section_lines.append("")
    final_body = stub_body + "\n".join(merged_section_lines) + "\n"

    # Delete every source page (except the canonical-slug one — we're rewriting it)
    for m in group.members:
        if m.path == canon_path:
            continue  # will be overwritten by write_frontmatter below
        try:
            subprocess.run(["git", "rm", "-q", str(m.path)],
                           cwd=wiki_root, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            m.path.unlink(missing_ok=True)

    write_frontmatter(canon_path, stub_fm, final_body)


def _split_stub(stub: str) -> tuple[dict, str]:
    """Parse a venue_md_stub() string into (fm dict, body)."""
    import io
    import yaml
    if not stub.startswith("---\n"):
        return {}, stub
    rest = stub[4:]
    end = rest.find("\n---\n")
    if end < 0:
        return {}, stub
    fm_text = rest[:end]
    body = rest[end + 5:]
    fm = yaml.safe_load(fm_text) or {}
    return fm, body
```

Then in `_run_apply` change the merge-skip line to call `_apply_merge`:

```python
def _run_apply(wiki_root: Path) -> int:
    plan, rewrites, report = _build_report(wiki_root)
    _write_report(wiki_root, report)

    for g in plan.groups:
        if g.is_merge:
            _apply_merge(wiki_root, g)
        else:
            _apply_rename(g)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/migrate-venues.py tests/test_migrate_venues_cli.py
git commit -m "$(cat <<'EOF'
feat(migrate-venues): --apply for multi-page merges

Write canonical page via venue_md_stub, archive every member's
body verbatim under '## Merged from', union aliases, delete
source pages. Existing canonical pages are merge members too —
their pre-existing body is archived alongside the others.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: `--apply` for paper-page rewrites

**Files:**
- Modify: `scripts/migrate-venues.py`
- Modify: `tests/test_migrate_venues_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_migrate_venues_cli.py`:

```python
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
    assert fm_a["updated"] == _today_iso()  # bumped

    # Unaffected paper byte-for-byte unchanged (modulo whitespace yaml.dump
    # may differ; instead verify venue is unchanged).
    fm_u, _ = read_frontmatter(tmp_git_wiki / "wiki/papers/pUnaffected.md")
    assert fm_u["venue"] == "ieee-transactions-on-communications"


def _today_iso():
    from datetime import date
    return date.today().isoformat()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py::test_apply_rewrites_paper_pages -v`
Expected: FAIL — paper page's `venue:` is still the old slug.

- [ ] **Step 3: Implement paper-page rewrite**

In `scripts/migrate-venues.py`, add a helper:

```python
def _apply_paper_rewrites(rewrites: list[PaperRewrite]) -> None:
    today = _today()
    for r in rewrites:
        fm, body = read_frontmatter(r.path)
        fm["venue"] = r.new_slug
        new_tags = []
        old_tag = f"venue/{r.old_slug}"
        new_tag = f"venue/{r.new_slug}"
        for t in fm.get("tags") or []:
            if t == old_tag:
                if new_tag not in new_tags:
                    new_tags.append(new_tag)
            else:
                new_tags.append(t)
        if new_tag not in new_tags:
            new_tags.append(new_tag)
        fm["tags"] = new_tags
        fm["updated"] = today
        write_frontmatter(r.path, fm, body)
```

Update `_run_apply`:

```python
def _run_apply(wiki_root: Path) -> int:
    plan, rewrites, report = _build_report(wiki_root)
    _write_report(wiki_root, report)

    for g in plan.groups:
        if g.is_merge:
            _apply_merge(wiki_root, g)
        else:
            _apply_rename(g)

    _apply_paper_rewrites(rewrites)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/migrate-venues.py tests/test_migrate_venues_cli.py
git commit -m "$(cat <<'EOF'
feat(migrate-venues): --apply rewrites paper venue: + venue/* tag

Walks PaperRewrite records collected from compute_plan, updates
each paper's venue: field and venue/* tag (preserving other
tags), bumps updated: to today. Papers pointing at unaffected
venues are untouched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: `--apply` preconditions: dirty tree refusal + snapshot tag + commit + log

**Files:**
- Modify: `scripts/migrate-venues.py`
- Modify: `tests/test_migrate_venues_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_migrate_venues_cli.py`:

```python
def test_apply_refuses_dirty_tree(tmp_git_wiki):
    _venue(tmp_git_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers", papers=["pA"])
    # Don't commit — leave the tree dirty
    result = run_migrate(tmp_git_wiki, "--apply")
    assert result.returncode != 0
    assert "dirty" in (result.stderr + result.stdout).lower() or "uncommitted" in (result.stderr + result.stdout).lower()
    # The lock should have been released
    assert not (tmp_git_wiki / ".lock").exists()


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: the three new tests FAIL.

- [ ] **Step 3: Implement preconditions, snapshot tag, commit, log**

In `scripts/migrate-venues.py`, add helpers:

```python
def _git(cwd: Path, *args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=capture, text=True, check=check,
    )


def _is_dirty(wiki_root: Path) -> bool:
    out = _git(wiki_root, "status", "--porcelain", check=False).stdout
    return bool(out.strip())


def _make_snapshot(wiki_root: Path) -> str:
    tag = f"snapshot/pre-venue-migration-{_today()}"
    # If the tag already exists from a prior aborted run, reuse it (don't fail)
    existing = _git(wiki_root, "tag", "-l", tag, check=False).stdout.strip()
    if not existing:
        _git(wiki_root, "tag", "-a", tag, "-m", f"pre-venue-migration {_today()}")
    return tag


def _append_log(wiki_root: Path, summary: str) -> None:
    log_path = wiki_root / "log.md"
    entry = f"\n## [{_today()}] migrate-venues | {summary}\n"
    if log_path.exists():
        log_path.write_text(log_path.read_text() + entry)
    else:
        log_path.write_text(f"# Log\n{entry}")


def _commit_all(wiki_root: Path, summary: str) -> None:
    _git(wiki_root, "add", "-A")
    _git(wiki_root, "commit", "-m", f"migrate: venue normalization ({summary})")
```

Update `_run_apply` to use them:

```python
def _run_apply(wiki_root: Path) -> int:
    if _is_dirty(wiki_root):
        print("ERROR: working tree is dirty (uncommitted changes); commit or stash first",
              file=sys.stderr)
        return 5

    plan, rewrites, report = _build_report(wiki_root)
    _write_report(wiki_root, report)
    if plan.skipped:
        print("ERROR: refusing to apply — some venue pages could not be normalized:",
              file=sys.stderr)
        for s in plan.skipped:
            print(f"  - {s}", file=sys.stderr)
        print("Fix these pages and re-run, or remove them from the wiki.", file=sys.stderr)
        return 6
    _make_snapshot(wiki_root)

    n_renames = sum(1 for g in plan.groups if not g.is_merge)
    n_merge_in = sum(len(g.members) for g in plan.groups if g.is_merge)
    n_merge_out = sum(1 for g in plan.groups if g.is_merge)

    for g in plan.groups:
        if g.is_merge:
            _apply_merge(wiki_root, g)
        else:
            _apply_rename(g)

    _apply_paper_rewrites(rewrites)

    summary = f"{n_merge_in}→{n_merge_out} merges, {n_renames} renames, {len(rewrites)} paper rewrites"
    _append_log(wiki_root, summary)
    _commit_all(wiki_root, summary)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/migrate-venues.py tests/test_migrate_venues_cli.py
git commit -m "$(cat <<'EOF'
feat(migrate-venues): preconditions + snapshot tag + log + commit

--apply now refuses a dirty tree, takes snapshot/pre-venue-
migration-<date>, appends a log.md entry, and commits everything
(report, venue pages, paper pages, log) in one shot.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: End-to-end idempotency

**Files:**
- Modify: `tests/test_migrate_venues_cli.py`

- [ ] **Step 1: Write the test**

Append to `tests/test_migrate_venues_cli.py`:

```python
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
    # No renames, no merges, no rewrites
    assert "0 renamed" in latest or "## Renames" not in latest
    assert "## Merges" not in latest
    # The asilomar canonical page is now a no-op (not in plan)


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
```

- [ ] **Step 2: Run tests**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_migrate_venues_cli.py -v`
Expected: all PASS, including the two new idempotency tests.

If `test_apply_twice_is_no_op` fails because `_commit_all` always creates a commit even when nothing changed, fix `_commit_all` to skip the commit when `git diff --cached --quiet` succeeds:

```python
def _commit_all(wiki_root: Path, summary: str) -> None:
    _git(wiki_root, "add", "-A")
    diff = _git(wiki_root, "diff", "--cached", "--quiet", check=False)
    if diff.returncode == 0:
        return  # nothing staged — no-op
    _git(wiki_root, "commit", "-m", f"migrate: venue normalization ({summary})")
```

Re-run the tests to confirm the fix.

- [ ] **Step 3: Run the entire test suite to confirm nothing else regressed**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest -x`
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/tung491/Work/academic_wiki
git add scripts/migrate-venues.py tests/test_migrate_venues_cli.py
git commit -m "$(cat <<'EOF'
test(migrate-venues): end-to-end idempotency

After --apply, both --dry-run and a second --apply are no-ops.
_commit_all skips the git commit when nothing is staged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Implementation notes for the engineer

- **Run individual tests with `-k` while iterating:** `pytest tests/test_venue_normalize.py -k worked_examples -v`.
- **The wiki's Python is run via the project's `.venv`** if one exists (`source .venv/bin/activate` or use `.venv/bin/python -m pytest`); otherwise the system `python3` is fine since dependencies are minimal.
- **Don't refactor `make_slug`.** This design wraps it. If you find a real bug in `make_slug` while testing, file it separately.
- **The dry-run report's "skipped" section is the user's repair queue.** When real-wiki migration is run, the user fixes parse errors before `--apply`. The migration itself doesn't try to repair them.
- **Acceptance** for shipping: after the test suite passes, run `python scripts/migrate-venues.py --wiki-path "$HOME/Documents/Obsidian Vault/03-Resources/academic" --dry-run` against the real wiki and eyeball the report. The expected counts (per the design doc): around 312 renames and ~28 merges across ~400+ pages.
