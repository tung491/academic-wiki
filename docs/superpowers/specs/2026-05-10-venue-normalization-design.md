# Venue Normalization Design

**Date:** 2026-05-10
**Status:** Draft — pending user review

## Problem

The wiki currently has 464 venue pages, many of which are different editions of the same conference series stored as separate pages. Examples:

- `2022-56th-asilomar-conference-on-signals-systems-and-computers`
- `2023-57th-asilomar-conference-on-signals-systems-and-computers`
- `2024-58th-asilomar-conference-on-signals-systems-and-computers`

Plus pairs like `aina-2004` vs `aina-2005`, multiple per-year `globecom`/`icc`/`wcnc`/`isit` editions, and so on. These should collapse to a single canonical venue page per series.

The compile flow generates venue slugs by passing the raw venue string straight through `make_slug()`, which preserves the year (e.g., `2022`) and ordinal prefix (e.g., `56th`) verbatim. Year is already captured by the `year/<YYYY>` tag on each paper, so leaving it in the venue slug is pure duplication.

## Goal

Make the venue slug edition-agnostic. Two papers from different editions of the same conference series produce the same `venue:` slug and link to the same `wiki/venues/<slug>.md` page.

## Approach (hybrid)

A deterministic Python normalization core handles the regular cases (year + ordinal stripping). A lint-only near-duplicate detector flags variant-spelling pairs that the deterministic rules can't auto-merge (e.g., `ieee-cic-...` vs `ieeecic-...`); auto-fix is out of scope for this design.

## Architecture & file layout

**New module:** `scripts/academic_wiki_lib/venue_normalize.py`

```
normalize_venue(raw: str) -> tuple[str, str]
    # Returns (canonical_name, slug). canonical_name preserves casing/punctuation
    # in human-readable form; slug is what make_slug would produce on the canonical name.

near_duplicate_pairs(slugs: Iterable[str], threshold: float = 0.92) -> list[tuple[str, str, float]]
    # For lint. Returns pairs (slug_a, slug_b, similarity) above threshold.
    # Symmetric: (a, b) appears once with a < b lexicographically.
```

**Touched modules:**

- `templates.py` — `venue_md_stub()` is unchanged; callers now pass `canonical_name` (from `normalize_venue`) as `name:` instead of the raw venue string.
- `slug.py` — unchanged. `normalize_venue` calls `make_slug` internally on its cleaned string.
- `lint-wiki.py` — new check: "Near-duplicate venue slugs" using `near_duplicate_pairs`. Threshold is a constant in the lint module, not a CLI flag.

**New CLI surface:** `scripts/migrate-venues.py` — standalone script (not part of the slash command). Args: `--wiki-path PATH`, `--dry-run` (default), `--apply`. Takes the wiki's `.lock`.

**Touched docs (LLM prompts read at compile time):**

- `skills/wiki/references/compilation-guide.md` — Step 4b
- `skills/wiki/references/batch-compile-prompt.md` — venue slug section
- `skills/wiki/references/batch-compile-full-prompt.md` — venue slug section
- `skills/wiki/references/entity-schemas.md` — note next to the venue schema

**No new dependencies.** Near-duplicate detection uses `difflib.SequenceMatcher` (stdlib).

## Normalization algorithm

`normalize_venue(raw: str) -> tuple[str, str]` runs these passes in order on the raw string.

```
Input:  "2022 56th Asilomar Conference on Signals, Systems, and Computers"

1. Unwrap parens — keep the inner content as inline text.
   "(AINA 2005)" → " AINA 2005 "
   No-op for Asilomar.

2. Strip ordinals — pattern: \b\d+(?:st|nd|rd|th)\b  (case-insensitive)
   "2022  Asilomar Conference on Signals, Systems, and Computers"

3. Strip 4-digit years — pattern: (?<![0-9])(19|20)\d{2}(?![0-9])
   The lookbehind/lookahead keeps "ICCC2024" matching but won't eat parts of
   longer digit runs. After year strip:
   "  Asilomar Conference on Signals, Systems, and Computers"

   Glued example: "VTC2022-Fall" → "VTC-Fall" (year matched between non-digit
   boundaries on both sides).

4. Collapse whitespace runs to a single space. Commas are preserved in the
   canonical name (worked example 1 requires "Signals, Systems, and Computers"
   to keep its commas). Strip leading/trailing commas, semicolons, and stray
   hyphens that lost a neighbor when the year/ordinal next to them was removed.

5. Compute canonical_name — trim, collapse internal whitespace to single space.
   canonical_name = "Asilomar Conference on Signals, Systems, and Computers"

6. Compute slug via a private `_venue_slug()` that mirrors `make_slug` (NFKD,
   ASCII-fold, lowercase, Greek transliteration, non-alphanumeric→hyphen,
   collapse hyphen runs, leading-stop-word filter) but **omits the 60-char
   truncation** because long conference names produce slugs above 60 chars
   (e.g., the AINA worked example is 81 chars). Reuses helpers from `slug.py`
   (`_transliterate`, `_strip_leading_stopword_if_remaining_multiword`) to
   avoid duplication.
   slug = "asilomar-conference-on-signals-systems-and-computers"
```

### Worked examples (test contract)

| Raw input | canonical_name | slug |
|---|---|---|
| `2022 56th Asilomar Conference on Signals, Systems, and Computers` | `Asilomar Conference on Signals, Systems, and Computers` | `asilomar-conference-on-signals-systems-and-computers` |
| `19th International Conference on Advanced Information Networking and Applications (AINA 2005)` | `International Conference on Advanced Information Networking and Applications AINA` | `international-conference-on-advanced-information-networking-and-applications-aina` |
| `2022 IEEE 96th Vehicular Technology Conference (VTC2022-Fall)` | `IEEE Vehicular Technology Conference VTC-Fall` | `ieee-vehicular-technology-conference-vtc-fall` |
| `2024 IEEE Globecom Workshops (GC Wkshps)` | `IEEE Globecom Workshops GC Wkshps` | `ieee-globecom-workshops-gc-wkshps` |
| `IEEE Transactions on Communications` | `IEEE Transactions on Communications` | `ieee-transactions-on-communications` |
| `arXiv preprint` | `arXiv preprint` | `arxiv-preprint` |

### Edge cases

- **Empty after stripping** (`"2024 21st"`, `"   "`, `""`) → raise `ValueError`. Caller treats it like a missing venue.
- **Year window 1900–2099 only.** `\b1899\b` and `\b2100\b` are kept. Avoids touching `802.11`, `4G`, `1900s` outside-the-window numerics.
- **Standalone non-year digits** (`5G`, `IPv6`, `802.11`) — not 4-digit `(19|20)NN` patterns, so unaffected.
- **Multiple acronym occurrences** (`(AINA 2005)`) — covered by paren-unwrap + year-strip; no special handling.
- **Trailing/leading commas** — stripped in step 4.
- **Spring/Fall/Workshops qualifiers** — preserved (only digits and ordinals are removed).

### Asymmetry note

`_venue_slug()` ASCII-folds Greek and applies a stop-word filter (drops leading `a`/`an`/`the`/`on`/`of`/`for`/`with` if the remainder is multi-word). Those rules apply to the slug. The `canonical_name` retains stop words, commas, and original casing — intentional, since it's the human-readable name on the venue page.

## Compile-time integration

Today, `compilation-guide.md` Step 4b runs:

```python
slug = make_slug(raw_venue)
venue_type = guess_venue_type(raw_venue)
# write venue_md_stub(slug=slug, name=raw_venue, venue_type=venue_type, ...)
```

After this change:

```python
canonical_name, slug = normalize_venue(raw_venue)
venue_type = guess_venue_type(canonical_name)   # was: raw_venue
# write venue_md_stub(slug=slug, name=canonical_name, ...)
```

**Three call sites get updated** — all in markdown the LLM reads:

1. `compilation-guide.md` Step 4b — replace the `make_slug` line; update the description of what gets written to `name:`.
2. `batch-compile-prompt.md` — replace the "Lowercase the full venue name…" instructions with: "Call `academic_wiki_lib.venue_normalize.normalize_venue(<raw-venue>)` to get `(canonical_name, slug)`. Use both — `slug` for the path/tag, `canonical_name` for the venue page's `name:` field and `# <heading>`."
3. `batch-compile-full-prompt.md` — same edit as #2.

**Tag follows slug.** The paper's `tags:` list already gets `venue/<slug>` deterministically. No change to that line — it picks up the new slug automatically.

**Paper page's `venue:` follows slug.** New compiles get the new slug. Old paper pages have old slugs — those are migration's job.

**Existing canonical-slug venue page → upsert path takes over.** Read existing page, append paper-id to `papers:`, union `field/*` tags, bump `updated:`. Compile stays idempotent.

**Existing non-canonical-slug venue page** (migration hasn't run) → compile creates a new canonical-slug page; the old page is orphaned. Acceptable: no worse than the status quo. Migration cleans up.

**Cite resolution & backlinks** — unaffected. Citations resolve by `paper-id`. Backlinks scan page titles, which are still distinctive.

**No change to ingest.** Ingest writes `raw/extracts/<paper-id>.md` with the raw `venue:` field for compile to consume. The raw extract keeps the raw venue string verbatim — that stays the source of truth, and compile re-normalizes on every run.

## Migration command

**Surface:** `python scripts/migrate-venues.py --wiki-path <path> [--dry-run | --apply]`

Default if neither flag given: `--dry-run`. `--apply` requires a clean working tree.

### Phases

1. **Acquire the wiki lock** (`<wiki>/.lock`). Fail if held.
2. **Scan** — read every `wiki/venues/*.md`. For each, parse frontmatter to get the existing `name:` and `slug:`. Compute the new `(canonical_name, new_slug)` from the existing `name:`. Build a plan:
   ```
   Plan = list[Group]
   Group = {
     new_slug: str,
     new_canonical_name: str,
     members: list[VenuePage],   # existing pages mapping to this new_slug
     new_papers: list[paper-id], # union of all members' papers
     new_tags:   list[str],      # union of all members' field/* tags
   }
   ```
   A group is a "no-op" only when `len(members) == 1` AND that single member's existing slug equals `new_slug`. If a canonical-slug page already exists *and* one or more non-canonical-slug pages normalize to the same `new_slug`, all of them are members of the same merge group — the canonical page is not skipped, it's merged into (its `papers:` and `tags:` get unioned with the others, its body becomes the "Merged from" anchor).
3. **Find paper-page rewrites** — for each member of every group, scan `wiki/papers/*.md` for any paper whose `venue: <old-slug>` or whose `tags:` contains `venue/<old-slug>`. Collect rewrites.
4. **Find near-duplicate pairs** — `near_duplicate_pairs(new_slugs)` on post-normalization slugs. Surface variant-spelling collisions in the report.
5. **Write the dry-run report** to `outputs/reports/<YYYY-MM-DD>-venue-migration.md` (format below).
6. **Stop here on `--dry-run`.** Print report path; release lock.
7. **On `--apply`:**
   1. Re-run phases 2–4 (scan, find rewrites, find near-duplicates) — do not trust a stale dry-run plan, since the wiki may have changed in the interim.
   2. Write the final applied report to `outputs/reports/<YYYY-MM-DD>-venue-migration.md` (overwrites any prior dry-run report from the same day; the prior version is recoverable via git).
   3. Tag `snapshot/pre-venue-migration-<YYYY-MM-DD>` on the wiki repo (rollback path).
   4. For each merge group, write the canonical page via `venue_md_stub(slug=new_slug, name=new_canonical_name, venue_type=<resolved>, paper_ids=<union>, field_tags=<union>, today=<today>)`. Append a "Merged from" body section listing each source's old slug, old name, and a verbatim copy of the source's body content.
   5. Collect merge-source slugs into the canonical page's `aliases:`.
   6. Delete the source pages from disk (their content is archived).
   7. For each rename (single-page group), `git mv` the file and rewrite `slug:` and `name:` frontmatter. Add the old slug to `aliases:`.
   8. For each paper-page rewrite, update `venue:` and the `venue/*` tag. Bump `updated:` to today.
   9. Append to `log.md`: `## [YYYY-MM-DD] migrate-venues | merged N→M, renamed K, rewrote P paper pages`.
   10. Single commit covering the report, venue page changes, paper page rewrites, and `log.md`: `migrate: venue normalization (N→M merges, K renames, P paper rewrites)`.
   11. Release lock.

### Dry-run report format

```markdown
# Venue Migration Plan — 2026-05-10

## Summary
- 464 existing venue pages
- 312 will be renamed to a new slug (no merge)
- 87 will merge into 28 canonical pages
- 65 are no-ops (already canonical)
- 41 paper pages need `venue:` rewrites; 41 need `venue/*` tag rewrites
- 3 near-duplicate slug pairs flagged for manual review (variant spellings)

## Renames (single-page groups)
- `2022-56th-asilomar-...` → `asilomar-conference-on-signals-systems-and-computers`
- ...

## Merges (multi-page groups)
### `asilomar-conference-on-signals-systems-and-computers` ← merges 4 pages
Sources:
- `2022-56th-asilomar-conference-on-signals-systems-and-computers` (3 papers)
- `2023-57th-asilomar-conference-on-signals-systems-and-computers` (5 papers)
- `2024-58th-asilomar-...` (2 papers)
- ...
New `papers:` list (union, deduped, 10 entries): [...]
New `tags:` list (union of field/*, 4 entries): [...]
New `name:` "Asilomar Conference on Signals, Systems, and Computers"
New `venue-type:` conference (existing — preserved if unanimous; otherwise flagged)

## Paper-page rewrites
- `vaswani2017attention.md`: venue: `nips-2017` → `nips`; tag `venue/nips-2017` → `venue/nips`
- ... (41 entries)

## Near-duplicates flagged for manual review
- `ieee-cic-international-conference-on-communications-in-china-iccc` ↔
  `ieeecic-international-conference-on-communications-in-china-iccc`
  (similarity 0.97)
- ...

## Skipped (could not parse frontmatter)
- ... (if any)
```

### Conflict resolution rules during merge

- **`venue-type:`** — if all members agree, use it. Otherwise, most common; ties broken by the page with the most `papers:`; if still tied, lex-smallest old slug wins. Conflicts logged in the report.
- **`created:`** — earliest across members.

### Idempotency

Re-running `--apply` after a successful migration is a no-op (plan reports 0 changes). Re-running on a dirty tree fails fast.

### Failure handling

No automatic rollback mid-apply. The pre-migration snapshot tag is the rollback path: `git -C <wiki> reset --hard snapshot/pre-venue-migration-<date>`. Documented in the script's `--help`.

### Stop conditions for `--apply`

- Lockfile held.
- Dirty git tree.
- Any venue page has unparseable frontmatter (dry-run flagged it; user must fix).
- `normalize_venue` raises `ValueError` for any existing venue's `name:`. Abort with the offending page.

Paper pages with `venue:` values that don't match any existing venue page are *not* a stop condition — those are pre-existing dead references that migration neither fixes nor breaks; lint is the right place to surface them, separately from this migration.

## Lint near-duplicate detection

After migration, the deterministic regex won't have caught spelling variants. A new lint check surfaces these for manual review.

```python
# academic_wiki_lib/venue_normalize.py
def near_duplicate_pairs(
    slugs: Iterable[str],
    threshold: float = 0.92,
) -> list[tuple[str, str, float]]:
    # Returns sorted list of (slug_a, slug_b, similarity) where similarity ≥ threshold.
    # Uses difflib.SequenceMatcher().ratio() on the *space-separated token list*
    # (slug split by '-'), so word-level edits weigh more than character-level.
    # Symmetric: (a, b) appears once with a < b lexicographically.
```

**Threshold choice.** 0.92 catches `ieee-cic` ↔ `ieeecic` (one missing hyphen → ~0.97 token-set similarity) without flagging genuinely distinct conferences.

**Acronym-suffix reinforcement.** If two slugs share the same trailing token (after splitting on `-`) AND have similarity ≥ 0.80, also flag them. Catches cases where the acronym matches but the prefix has more drift. (0.80 was empirically calibrated; matching-acronym variant pairs score ~0.83–0.97 while distinct conferences sharing common words score ~0.72.)

**Lint report integration:**

```markdown
## Near-duplicate venue slugs (2 candidates)

These pairs may represent the same venue with spelling variants. Review and either:
- Manually merge by editing the canonical page's frontmatter, deleting the
  duplicate, and adding the old slug to `aliases:`, OR
- Confirm they are distinct (no action; the warning recurs on the next lint).

- `ieee-cic-international-conference-on-communications-in-china-iccc` ↔
  `ieeecic-international-conference-on-communications-in-china-iccc`
  (similarity 0.97; matching acronym suffix `iccc`)
```

**Performance.** O(N²) over ~400 slugs ≈ 80k comparisons; `SequenceMatcher.ratio()` runs in a few seconds. Fine.

## Testing strategy

Tests live under `tests/`, matching the existing layout (`tests/test_slug.py` already exists for `make_slug`).

### `tests/test_venue_normalize.py` — unit tests for `normalize_venue`

- **Worked-examples table** (parametrized) asserting both `canonical_name` and `slug` for each row in the table above. This is the contract.
- **Year-stripping edge cases:** `5G NR` keeps `5g-nr`; `802.11` keeps `802-11`; `4G LTE` keeps `4g-lte`; `VTC2022-Fall` → `vtc-fall`; `WCNC2023` → `wcnc`; `GLOBECOM 1899` keeps `globecom-1899`; `ICASSP 2100` keeps `icassp-2100`.
- **Ordinal edge cases:** `21st century` → `century`; `3rd-party tool` → `party-tool`; `Section 1st` → `section`.
- **Paren/bracket unwrap:** `(AINA 2005)`, `[AINA 2005]`, `AINA (2005)` produce the same canonical.
- **Empty after stripping:** `2024 21st`, `   `, `""` raise `ValueError`.
- **Idempotency property test:** for every row in the table, `normalize_venue(normalize_venue(raw)[0])[0] == normalize_venue(raw)[0]`. This is what makes compile re-runs safe.

### `tests/test_near_duplicate.py` — unit tests for `near_duplicate_pairs`

- True positives: `ieee-cic-...` ↔ `ieeecic-...` flagged.
- True negatives: `ieee-international-conference-on-communications` ↔ `ieee-international-conference-on-image-processing` NOT flagged.
- Acronym-suffix reinforcement: matching trailing acronym + similarity 0.86 is flagged (would not be on threshold alone).
- Symmetry: `(a, b)` appears with `a < b` only.
- Empty / single-element input returns `[]`.

### `tests/test_migrate_venues.py` — integration tests

Each test builds a fixture wiki in `tmp_path` with hand-written venue and paper pages, runs the script, and asserts resulting state.

- **Dry-run is read-only.** Report file written; no other files changed (dirhash before/after).
- **Single-page rename.** File renamed, `slug:`/`name:` updated, `aliases:` contains old slug, paper's `venue:` and `venue/*` tag rewritten, single commit, snapshot tag exists.
- **Multi-page merge.** 1 canonical page with union `papers:` (deduped, lex-sorted) and union `field/*` tags; "Merged from" body section with each source's verbatim body; sources gone; all old slugs in `aliases:`.
- **Idempotency.** After `--apply`, re-running `--dry-run` reports zero changes; re-running `--apply` is a no-op.
- **Dirty tree refusal.** `--apply` aborts; doesn't take the lock.
- **Lock held refusal.** Both `--dry-run` and `--apply` fail.
- **`venue-type:` conflict resolution.** `conference, conference, journal` → canonical gets `conference`; report flags conflict.
- **`created:` earliest-wins.** Earliest date across members is preserved.
- **Paper-page rewrite scope.** Only paper pages whose `venue:` matches an old slug are touched; unaffected papers are byte-identical before/after.

### No tests for compile-time integration

The compile flow is LLM-driven from a markdown prompt. Verifying it is a documentation/prompt-engineering concern, not an automated test. The unit-test contract on `normalize_venue` is what the prompt depends on.

### Test data isolation

All fixtures use `tmp_path` and `git init` a fresh repo per test. No reliance on the user's actual Obsidian vault.

### Run-it-once acceptance

After implementation: run `migrate-venues.py --dry-run` against the real `~/Documents/Obsidian Vault/03-Resources/academic/` wiki, eyeball the report, confirm merge counts. Then run `--apply`. On the user's checklist, not in CI.

## Risks

- **Body-archive on merge can be large.** 4 pages × 200 lines each → ~800-line canonical body. Acceptable: archival > silent loss. User can prune later.
- **Aliases can collide.** Two source pages might share a value in their existing `aliases:`. Migration unions and dedupes — first-seen wins. Logged.
- **Migrating before user-edited venue prose accumulates** is the cheap path. Recommend running migration soon after this design ships.
- **Year-floor/ceiling drift.** `1900–2099` will need an update before 2100 — comment in `venue_normalize.py` flagging this.
- **Lint near-duplicate noise on fresh-migrated wiki.** First post-migration lint flags every variant-spelling pair; user triages once. After that, only new variants from new ingests trigger fresh flags.

## Non-goals

- Auto-merging variant-spelling pairs. Lint flags only.
- LLM-assisted migration. Pure deterministic.
- Cross-language synonyms.
- Author-name or paper-id normalization. Venue-only.
- Changing `make_slug` itself. Venue normalization wraps it.
- Backwards compatibility with hand-typed `[[old-venue-slug]]` wikilinks in user notes. Lint's existing alias-resolution check covers this once `aliases:` is populated by migration.

## Open assumptions

1. Every existing venue page's frontmatter has a parseable `name:` field. Dry-run report includes a "Skipped (could not parse)" section for malformed pages. Those need manual repair before `--apply`.
2. The `papers:` lists in venue page frontmatter are accurate. Migration trusts them — does *not* re-derive `papers:` by scanning paper pages.
3. The wiki's git repo is in a sane state when `--apply` runs. Enforced by the dirty-tree refusal.
