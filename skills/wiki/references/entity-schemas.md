# Entity Schemas (verbatim from spec §§3.1-3.6)

Reference for `compile` (full tier, Wave 2). Verbatim from `docs/superpowers/specs/2026-04-16-academic-wiki-design.md`.

---

## §3.1 Primary entities

**paper** — `wiki/papers/<paper-id>.md`

```yaml
---
paper-id: vaswani-2017-attention            # canonical internal ID (stable, never rewrites)
citation-key: vaswani2017attention          # derived, used for BibTeX export; may change
type: paper
status: queued | skimmed | read | deep-read
created: YYYY-MM-DD                         # first ingest date
updated: YYYY-MM-DD                         # last material update
publication-date: YYYY-MM-DD                # optional, if known
title: "Attention Is All You Need"
authors:                                    # full objects — slug + human name + optional ORCID
  - {slug: ashish-vaswani, name: "Ashish Vaswani"}
  - {slug: noam-shazeer, name: "Noam Shazeer"}
year: 2017
venue: nips                                 # slug; human name stored on the venue page if one exists
identifiers:                                # all known identifiers for this paper (used for dedup)
  doi: 10.xxx/xxx
  arxiv: 1706.03762
  arxiv-version: v5                         # specific arXiv version, if applicable
  url: https://...
aliases: []                                 # alternate paper-ids this page was previously known as
source-version: arxiv-v5                    # which source this wiki page summarizes
relationships:                              # optional — relations to other papers
  preprint-of: null                         # paper-id of the journal version
  version-of: null                          # paper-id of the canonical work (if this is a specific version)
  supersedes: []                            # paper-ids this supersedes
bib-file: raw/bib/vaswani-2017-attention.bib
extract: raw/extracts/vaswani-2017-attention.md
notes: raw/notes/vaswani-2017-attention.md  # optional — only if user wrote notes
figures: raw/figures/vaswani-2017-attention/  # optional
references-raw:                             # unresolved bibliography (verbatim from paper)
  - "Bahdanau, D. et al. 'Neural Machine Translation by Jointly Learning to Align and Translate.' 2014."
  - "Cho, K. et al. 'Learning Phrase Representations...' 2014."
cites:                                      # resolved references — paper-ids in this wiki
  - bahdanau-2014-neural
  - cho-2014-learning
tags: [field/nlp, method/attention, year/2017, venue/nips]
---
```

Body sections: `Metadata` / `Summary` / `Key Contributions` / `Methods` / `Results` / `Claims` / `User Notes` / `See Also`. User-notes section is auto-filled from `raw/notes/<paper-id>.md` if present.

Notes on the identity model:
- `paper-id` is generated on first ingest (see §5.2). Format mirrors the BibTeX key style for readability but is explicitly hyphen-separated to distinguish it from `citation-key`: `<lastname>-<year>-<firstword>`.
- `citation-key` (BibTeX-native, no hyphens: `vaswani2017attention`) is a derived export field. If metadata is corrected later, `citation-key` updates without renaming files.
- `identifiers:` is the dedup key. Ingest checks all existing papers' `identifiers:` against the incoming source — a match on any non-empty identifier (`doi`, `arxiv`, `url`, or `source-sha`) means the paper already exists; ingest merges new identifiers into the existing record instead of creating a duplicate.
- `aliases:` records historical `paper-id` values if the canonical id is ever renamed (e.g., metadata correction changes the first author). Wikilinks to the old id still resolve via alias lookup during lint.

Non-paper entities use `paper-id` values (not `citation-key`) in all reference fields like `sources:`, `supports:`, `evidence-for:`, etc.

**concept** — `wiki/concepts/<slug>.md`

```yaml
---
type: concept
status: active | stale
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [vaswani-2017-attention, ...]            # paper-ids
tags: [field/..., ...]
---
```

Body: `Definition` / `Details` / `See Also` / `Counter-Arguments and Gaps`.

**method** — `wiki/methods/<slug>.md`

```yaml
---
type: method
status: active | deprecated | contested
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, paper-id-2]
related-methods: [other-method-slug]
tags: [field/..., method/..., ...]
---
```

Body: `Definition` / `How It Works` / `Results Using This Method` / `Known Limitations` / `See Also` / `Counter-Arguments and Gaps`.

**open-problem** — `wiki/open-problems/<slug>.md`

```yaml
---
type: open-problem
status: open | partially-resolved | resolved | disputed
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, ...]
resolved-by: paper-id                             # optional
tags: [field/..., ...]
---
```

Body: `Statement` / `Why It Matters` / `Current Approaches` / `What's Missing` / `See Also`.

**result** — `wiki/results/<slug>.md` (cross-paper only)

```yaml
---
type: result
status: replicated | contested | preliminary | unverified
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, paper-id-2, ...]
refutes: [other-result-slug]
supports: [claim-slug]
tags: [field/..., method/..., ...]
---
```

Body: `Statement` / `Evidence` / `Conditions` / `Caveats` / `See Also`.

**claim** — `wiki/claims/<slug>.md` (cross-paper only)

```yaml
---
type: claim
status: established | contested | fringe | deprecated
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, ...]
evidence-for: [result-slug, ...]
evidence-against: [result-slug, ...]
tags: [field/..., ...]
---
```

Body: `Statement` / `Evidence For` / `Evidence Against` / `Open Questions` / `See Also`.

---

## §3.2 Secondary entities (on demand)

**author** — `wiki/authors/<slug>.md`

```yaml
---
type: author
name: "Ashish Vaswani"                            # human-readable
slug: ashish-vaswani
orcid: 0000-...
affiliation: ...
created: YYYY-MM-DD
updated: YYYY-MM-DD
papers: [paper-id-1, paper-id-2, ...]
tags: [field/..., person]
---
```

**venue** — `wiki/venues/<slug>.md`

```yaml
---
type: venue
name: "Conference on Neural Information Processing Systems"   # human-readable
slug: nips
venue-type: conference | journal | workshop | preprint-server
created: YYYY-MM-DD
updated: YYYY-MM-DD
papers: [paper-id-1, ...]
tags: [field/...]
---
```

---

## §3.3 Operational entity

**query-output** — `wiki/queries/<slug>.md`

```yaml
---
type: query-output
question: "<original question>"
status: filed | promoted
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, ...]
tags: [field/...]
---
```

---

## §3.4 Cross-schema conventions

1. **`sources:` vs `cites:` vs `references-raw:`** — three layered concepts:
   - `references-raw:` (paper pages only): the raw bibliography as captured from the source, unresolved.
   - `cites:` (paper pages only): the subset of `references-raw:` that has been resolved to `paper-id`s in the wiki. Every key in `cites:` must match an existing paper page; unmatched raw references stay only in `references-raw:` until their papers are ingested.
   - `sources:` (every non-paper entity): paper-ids that inform this page.
2. **References are by `paper-id`, not `citation-key`.** `citation-key` is presentation-only; internal graph references are all `paper-id`.
3. **Status fields are entity-specific.** Different entity types have different meaningful states.
4. **`cited-by:` is never stored.** Dataview computes it on demand from `cites:` fields.
5. **Result/claim pages exist only when cross-paper.** Single-paper results/claims stay inline in the paper page until promoted.
6. **User notes are referenced, not copied.** The paper page's "User Notes" section links and summarizes `raw/notes/<paper-id>.md`; it never embeds or overwrites.
7. **`created:` vs `updated:`** — `created:` is set on page birth and never changes. `updated:` is bumped on any material content change. Lint uses `updated:` for staleness checks.

---

## §3.5 Slug generation rules

Applies to all non-paper entity pages (paper pages use `paper-id`). Concept/method/open-problem/claim/result/author/venue slugs are derived deterministically from a title string:

1. Unicode NFKD normalize, strip combining marks (ASCII-fold): `"SIC'19 Paper" → "SIC'19 Paper"` (unchanged); `"α-divergence" → "a-divergence"`.
2. Lowercase.
3. Replace any run of non-alphanumeric characters (except existing hyphens) with a single hyphen.
4. Collapse consecutive hyphens to one; strip leading/trailing hyphens.
5. Truncate at 60 chars at a word boundary if possible.
6. **Stop-word filter** — drop leading `a`/`an`/`the`/`on`/`of`/`for`/`with` if and only if the result is ≥2 words.
7. Collision resolution: if `<slug>.md` already exists in the same subfolder, check whether the existing page's subject is the same (LLM judgment: same concept/method/etc. with a different phrasing — merge instead of creating). If genuinely distinct, append suffix `-2`, `-3`, ....
8. Aliases: when a slug is merged or renamed, add the former slug to the target page's frontmatter `aliases: []`. Lint resolves `[[old-slug]]` via alias lookup.

Examples:
- `"Rate-Splitting Multiple Access"` → `rate-splitting-multiple-access`
- `"The Attention Mechanism"` → `attention-mechanism` (stop-word dropped)
- `"O(n²) complexity of self-attention"` → `o-n2-complexity-of-self-attention` (non-alphanumeric runs collapse to hyphens; `²` is NFKD-folded to `2`)
- `"K-means"` → `k-means`

---

## §3.6 Update conflict policy

When a new source contributes information that overlaps with an existing entity page, the compile flow merges rather than overwrites:

1. **Preserve prior claims** — existing assertions are not deleted by a new source alone.
2. **Append new evidence** — add the new source to `sources:` and add content in a new paragraph or section, clearly attributed.
3. **Flag contradictions inline** — if the new source asserts something in tension with existing content, add an Obsidian callout:
   ```
   > [!WARNING] Contradiction with [[other-paper-id]]
   > <Paper A> says X, but <Paper B> says Y. Needs resolution.
   ```
   Do not silently overwrite either side.
4. **Never replace without provenance** — every material claim on a wiki page must be traceable to at least one paper-id in `sources:`. If an LLM cannot attribute a claim to a source, the claim is dropped or marked `status: stale`.
5. **Bump `updated:` frontmatter** after any merge.
6. **Log the merge** — compile's commit message summarizes: `compile: merged <new-paper-id> into <N> existing pages`.
