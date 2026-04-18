"""Templates for wiki initialization.

claude_md uses `.replace("{{NAME}}", name)` rather than f-string because Task 1.10
will inline spec content with YAML braces (e.g., `authors: [{slug: x, name: Y}]`)
that would break f-string parsing.
"""
from __future__ import annotations


def all_subdirs() -> list[str]:
    """All directories init should create beneath the wiki root (relative paths).

    Matches the 16 subdirectories in spec §2.2.
    """
    return [
        "raw/papers", "raw/extracts", "raw/bib", "raw/figures", "raw/notes",
        "wiki/papers", "wiki/concepts", "wiki/methods", "wiki/open-problems",
        "wiki/claims", "wiki/results", "wiki/authors", "wiki/venues", "wiki/queries",
        "outputs/reports", "outputs/bib",
    ]


INDEX_MD = """# {name} Wiki Index

Last updated: YYYY-MM-DD

<!-- Populated by compile. Format:
## field/<field-name>
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

The wiki is **its own git repository** (nested inside the Obsidian vault), not part of the vault's git history. This gives clean, atomic snapshots of only wiki state, independent of unrelated vault changes. See §2.3 for rationale and §5.7 for snapshot semantics.

```
{{NAME}}/                             # self-contained git repo (nested in vault)
├── .git/                             # the wiki's own git history
├── raw/                              # immutable; LLM reads, never edits
│   ├── papers/                       # source files: <paper-id>.pdf / .tex / .html / .md
│   ├── extracts/                     # LLM-readable text/LaTeX extracts: <paper-id>.md
│   ├── bib/                          # per-paper BibTeX: <paper-id>.bib
│   ├── figures/                      # per-paper figures: <paper-id>/fig-N.png
│   └── notes/                        # user's manual reading notes: <paper-id>.md (optional)
├── wiki/                             # LLM-owned synthesis
│   ├── index.md                      # catalog
│   ├── papers/                       # <paper-id>.md (paper-id is the canonical key; see §3.1)
│   ├── concepts/                     # <slug>.md
│   ├── methods/                      # <slug>.md
│   ├── open-problems/                # <slug>.md
│   ├── claims/                       # cross-paper only
│   ├── results/                      # cross-paper only
│   ├── authors/                      # on demand
│   ├── venues/                       # on demand
│   └── queries/                      # filed query answers
├── outputs/
│   ├── reports/                      # YYYY-MM-DD-lint.md
│   └── bib/                          # YYYY-MM-DD-<label>.bib
├── CLAUDE.md                         # authoritative schema
├── log.md                            # append-only ops log
├── .lock                             # advisory lockfile; prevents concurrent mutating ops
├── .gitignore
└── qmd.yml                           # optional; used if qmd is installed
```

The vault's own `.git` (if present) should ignore this nested repo. `init` writes a `.gitignore` entry in the vault root if it doesn't already exclude `03-Resources/<name>/`.

## Identity Model

**`paper-id` is the canonical key**. It is a stable internal identifier assigned on first ingest and used everywhere — filenames, frontmatter, wikilinks, and BibTeX `@key` (§3.1). This is the fix for "same paper ingested via arXiv ID and via DOI" deduplication.

**paper** — `wiki/papers/<paper-id>.md`

```yaml
---
paper-id: vaswani2017attention              # canonical internal ID (stable, never rewrites)
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
bib-file: raw/bib/vaswani2017attention.bib
extract: raw/extracts/vaswani2017attention.md
notes: raw/notes/vaswani2017attention.md    # optional — only if user wrote notes
figures: raw/figures/vaswani2017attention/  # optional
references-raw:                             # unresolved bibliography (verbatim from paper)
  - "Bahdanau, D. et al. 'Neural Machine Translation by Jointly Learning to Align and Translate.' 2014."
  - "Cho, K. et al. 'Learning Phrase Representations...' 2014."
cites:                                      # resolved references — paper-ids in this wiki
  - bahdanau2014neural
  - cho2014learning
tags: [field/nlp, method/attention, year/2017, venue/nips]
---
```

Body sections: `Metadata` / `Summary` / `Key Contributions` / `Methods` / `Results` / `Claims` / `User Notes` / `See Also`. User-notes section is auto-filled from `raw/notes/<paper-id>.md` if present.

Notes on the identity model:
- `paper-id` is generated on first ingest (see §5.2). Format: `<lastname><year><firstword>`.
- `identifiers:` is the dedup key. Ingest checks all existing papers' `identifiers:` against the incoming source — a match on any non-empty identifier (`doi`, `arxiv`, `url`, or `source-sha`) means the paper already exists; ingest merges new identifiers into the existing record instead of creating a duplicate.
- `aliases:` records historical `paper-id` values if the canonical id is ever renamed (e.g., metadata correction changes the first author). Wikilinks to the old id still resolve via alias lookup during lint.

Non-paper entities use `paper-id` values in all reference fields like `sources:`, `supports:`, `evidence-for:`, etc.

## Entity Types

### paper

`wiki/papers/<paper-id>.md` — see Identity Model section above for full schema.

### concept

`wiki/concepts/<slug>.md`

```yaml
---
type: concept
status: active | stale
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [vaswani2017attention, ...]              # paper-ids
tags: [field/..., ...]
---
```

Body: `Definition` / `Details` / `See Also` / `Counter-Arguments and Gaps`.

### method

`wiki/methods/<slug>.md`

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

### open-problem

`wiki/open-problems/<slug>.md`

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

### result

`wiki/results/<slug>.md` (cross-paper only)

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

### claim

`wiki/claims/<slug>.md` (cross-paper only)

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

### author (secondary, on demand)

`wiki/authors/<slug>.md`

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

### venue (secondary, on demand)

`wiki/venues/<slug>.md`

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

### query-output (operational)

`wiki/queries/<slug>.md`

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

## Cross-Schema Conventions

1. **`sources:` vs `cites:` vs `references-raw:`** — three layered concepts:
   - `references-raw:` (paper pages only): the raw bibliography as captured from the source, unresolved.
   - `cites:` (paper pages only): the subset of `references-raw:` that has been resolved to `paper-id`s in the wiki. Every key in `cites:` must match an existing paper page; unmatched raw references stay only in `references-raw:` until their papers are ingested.
   - `sources:` (every non-paper entity): paper-ids that inform this page.
2. **All internal references use `paper-id`.**
3. **Status fields are entity-specific.** Different entity types have different meaningful states.
4. **`cited-by:` is never stored.** Dataview computes it on demand from `cites:` fields.
5. **Result/claim pages exist only when cross-paper.** Single-paper results/claims stay inline in the paper page until promoted.
6. **User notes are referenced, not copied.** The paper page's "User Notes" section links and summarizes `raw/notes/<paper-id>.md`; it never embeds or overwrites.
7. **`created:` vs `updated:`** — `created:` is set on page birth and never changes. `updated:` is bumped on any material content change. Lint uses `updated:` for staleness checks.

## Slug Generation

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

## Update Conflict Policy

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

## Raw-Side Metadata Schema

Raw-side metadata lives in `raw/extracts/<paper-id>.md` frontmatter. These fields are written by `ingest` and are read-only for `compile`/`query`/`lint`.

```yaml
---
paper-id: vaswani2017attention
source-path: raw/papers/vaswani2017attention.pdf
source-sha: 3f8c1e...                       # SHA-256 of the source file; used for dedup
source-version: arxiv-v5                    # arXiv version, DOI version, publisher revision, etc.
source-type: pdf | html | latex | markdown
source-url: https://arxiv.org/pdf/1706.03762v5.pdf
extractor: ocr-papers-to-latex              # name of extractor used
extractor-version: 1.2.0                    # if the extractor reports a version
extracted-at: YYYY-MM-DDTHH:MM:SSZ          # ISO-8601 UTC timestamp
ocr-used: true | false
extract-status: complete | partial | failed
extract-warnings: []                        # list of LLM or extractor warnings
---
```

Purpose:
- `source-sha` is compared on every ingest; an exact match means this source has already been ingested (skip with a warning, or merge identifiers into the existing paper).
- `extractor-version` + `extract-status` tell the LLM whether the extract is trustworthy and whether to suggest re-extracting.
- `extract-warnings` captures things like "Figures 3-5 failed to render" or "Pages 8-10 have low OCR confidence" — consumed by lint.

## Tag Taxonomy

### Reserved Prefixes

| Prefix | Purpose | Examples | Auto-applied |
|---|---|---|---|
| `field/*` | Major research field | `field/wireless-comms`, `field/nlp` | Yes (during compile) |
| `subfield/*` | Narrower slice | `subfield/rsma`, `subfield/attention` | Yes (during compile) |
| `method/*` | Technique discussed | `method/rsma`, `method/transformer` | Yes (during compile) |
| `year/*` | Publication year | `year/2017`, `year/2024` | Yes (on paper creation) |
| `venue/*` | Venue slug | `venue/nips`, `venue/globecom` | Yes (on paper creation) |
| `project/*` | User's research project | `project/rsma-survey-2025` | **No — user-only** |
| `user/*` | Personal workflow flag | `user/to-reread`, `user/must-cite` | **No — user-only** |

### Free-Form Tags

Allowed without a prefix. Examples: `foundational`, `survey`, `tutorial`, `position-paper`, `benchmark`, `reproducibility-study`.

### Rules

1. Paper pages get `field/*`, `subfield/*`, `method/*`, `year/*`, `venue/*` from the LLM during compile.
2. Concept / method / open-problem / claim / result pages get `field/*` and `subfield/*` aggregated from their `sources:` paper pages.
3. `project/*` and `user/*` are user-driven; the LLM may suggest them but never applies them silently.
4. Lint fails if any paper / concept / method / open-problem / claim / result lacks ≥1 `field/*` tag.
5. Tag renames are a manual concern for now — future tooling may automate.

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

Every page links to ≥1 other page when content warrants it. During `compile`, a backlink audit scans for page titles referenced in other wiki files; it inserts `[[wikilink]]` only when the matched slug is ≥2 words (avoids common single-word pollution like `[[attention]]` or `[[method]]`), OR when the page title appears within a noun phrase the LLM recognizes as a proper named entity. Common-word slugs can still be manually linked; they are not auto-linked by the audit. When a new source asserts something in tension with existing content, add an Obsidian callout:

```
> [!WARNING] Contradiction with [[other-page]]
> <Paper A> says X, but <Paper B> says Y. Needs resolution.
```

Do not silently overwrite either side of a contradiction. Lint collects and lists all `[!WARNING]` contradiction markers.

## Init Rules

Scaffolds a new wiki at `~/ObsidianVault/03-Resources/<name>/` (default `academic`). The wiki is created as its own nested git repository.

1. Abort if target exists (suggest `remove <name>` first).
2. Create full directory tree (§2.2).
3. `git -C <wiki-path> init` to start the nested repo.
4. Write `CLAUDE.md` with the complete schema (§§2–7 inline, ~1000–1200 lines).
5. Write `wiki/index.md`, `log.md`, `.gitignore`, `qmd.yml`.
6. Update the Obsidian vault's `.gitignore` (if one exists) to exclude `03-Resources/<name>/` so the vault's git doesn't try to track the nested repo. Log a note if the vault isn't itself a git repo.
7. Initial commit **inside the wiki's own repo**: `git -C <wiki-path> add . && git -C <wiki-path> commit -m "init: <name> wiki"`.
8. If qmd available: `qmd collection add <wiki-path>/wiki --name <name> && qmd embed --collection <name>`.
9. Print Web Clipper + Zotero export setup hints.

## Ingest Rules

Saves a source to `raw/`, generates an extract, stubs BibTeX, and assigns a canonical `paper-id`. Does **not** create wiki pages — `compile` does.

**Input routing** (autodetect):

- `^\d{4}\.\d{4,5}(v\d+)?$` → arXiv ID → `mcp__agentic-rag-v2__download_arxiv`
- `^10\.\d+/.+` → DOI → `mcp__agentic-rag-v2__doi2content`
- `arxiv.org/abs/...` or `arxiv.org/pdf/...` → extract ID (including version) → arXiv handler
- Publisher URL → `mcp__agentic-rag-v2__fetch_publisher_html`
- Local `.pdf` → `ocr-papers-to-latex` skill
- Local `.md` → treat as pre-extracted
- Anything else → ask user

**Pipeline**:

1. **Acquire lockfile**: take `{{NAME}}/.lock` (see §8). If already held, fail with `another operation is in progress`.
2. **Route input, acquire raw bytes/text.**
3. **Compute `source-sha`** — SHA-256 over the raw file. This is the cheapest dedup key.
4. **Dedup check — pass 1 (byte-level)**: scan existing `raw/extracts/*.md` for matching `source-sha`. If found, print: `"This exact source was already ingested as <paper-id>. Skipping."` Release lock; exit.
5. **Extract metadata** from the content:
    - First-author last name (lowercased, ASCII-folded: `García` → `garcia`).
    - 4-digit publication year.
    - Title's first meaningful word (lowercased; skip `a`/`an`/`the` and numerals).
    - Any known identifiers: `doi`, `arxiv` (with version if present), canonical `url`.
6. **Dedup check — pass 2 (identifier-level)**: compare extracted identifiers against every existing paper page's `identifiers:`. If any identifier matches (same DOI, same arXiv ID ignoring version, same canonical URL):
    - This paper already exists. Load its `paper-id`.
    - Merge: add any new identifiers the incoming source provides; if the incoming `source-version` differs, treat as a new version of the same paper (see step 8).
    - Do NOT create a new paper entity; re-use the existing `paper-id`.
7. **If no match (truly new paper)**: generate `paper-id` as `<lastname><year><firstword>`. Collision: if the id is already taken by a different paper (different identifiers), append `2`, `3`, ...
8. **Handle versions**: if the new source is a different version of an already-known paper (e.g., existing paper at arXiv v3, incoming is v5):
    - Save the new source file and extract with the same `paper-id` basename but store `source-version: arxiv-v5` in the extract frontmatter.
    - Append the new source to a per-paper-id manifest: `raw/extracts/<paper-id>.versions.yml` listing every version ingested with its `source-sha`, `extracted-at`, and `source-path`.
    - `wiki/papers/<paper-id>.md` updates `identifiers.arxiv-version:` to the most recent; older versions remain referenced in the manifest.
9. **Metadata-extraction failure fallback** (scan without OCR-able text, garbage metadata): use fallback `paper-id` of `unknown<YYYY><filenameslug>` for ALL file basenames consistently; set `metadata-incomplete: true` in the extract frontmatter; log for lint.
10. **Save files** with `<paper-id>` as the common basename across `raw/papers/`, `raw/extracts/`, `raw/bib/`, `raw/figures/`.
11. **Write extract frontmatter** per §3.7 with `source-sha`, `extractor`, `extracted-at`, `source-version`, etc.
12. **BibTeX**: if the source came with BibTeX (identifier-based ingest), save to `raw/bib/<paper-id>.bib`; otherwise stub a minimal `@misc` entry with `bib-incomplete: true`. BibTeX `@key` field uses `paper-id`.
13. **Append to `log.md`**: `## [YYYY-MM-DD] ingest | <paper-id>` with one-line summary (new paper, new version, or deduped).
14. **Commit**: `ingest: <paper-id>` (or `ingest: <paper-id> (new version v5)` / `ingest: deduped <paper-id>`).
15. **Release lockfile.**
16. **Print**: `Source saved with paper-id <paper-id>. Run wiki compile <paper-id> to integrate into the wiki.`

## Compile Rules

Default compile runs the full pipeline (paper pages + entity extraction + `cites:` resolution + backlink audit + cross-paper detection + index rebuild). `--paper-only` skips entity extraction through cross-paper detection.

**`compile [<paper-id>] [--paper-only]`**:

1. Acquire `{{NAME}}/.lock`.
2. Identify sources: given `<paper-id>` or all paper-ids in `raw/extracts/` without a matching `wiki/papers/<paper-id>.md`.
3. For each source:
    - Read `raw/extracts/<paper-id>.md` + `raw/notes/<paper-id>.md` if present.
    - Write/update `wiki/papers/<paper-id>.md` per §3.1. Populate `Summary`, `Key Contributions`, `Methods`, `Results`, `Claims`, `User Notes` sections inline.
    - `references-raw:` is populated from the bibliography section of the extract.
4. **Entity extraction** (skipped with `--paper-only`): identify concepts, methods, open-problems from the extract. Create/update `wiki/concepts/<slug>.md`, `wiki/methods/<slug>.md`, `wiki/open-problems/<slug>.md` per §3 schemas and §3.5 slug rules. Append `paper-id` to each page's `sources:`. Apply the update conflict policy (§3.6).
5. **Claim/result drafting**: draft claims and results as inline sections in the paper page.
6. **`cites:` resolution** (skipped with `--paper-only`): LLM fuzzy-matches entries in `references-raw:` against existing `wiki/papers/` by title + first author + year. Matches populate `cites:`. Unmatched entries remain only in `references-raw:` and surface in lint as candidate new ingests.
7. **Backlink audit with allowlist** (skipped with `--paper-only`): `grep -rln` to find page titles in other wiki files, but ONLY insert `[[wikilink]]` when:
    - the matched slug is ≥2 words (avoids common single-word pollution like `[[attention]]` or `[[method]]`), OR
    - the page title appears within a noun phrase recognized by the LLM as a proper named entity.
    Common-word slugs can still be manually linked; they just aren't auto-linked by the audit.
8. **Cross-paper candidate detection** (skipped with `--paper-only`) — NO silent auto-promotion. Use LLM judgment on semantic equivalence to identify candidates where a claim/result in this paper overlaps with one in another paper's Claims/Results section. Write candidates to a scratch file `outputs/reports/YYYY-MM-DD-promotion-candidates.md` with proposed slug, source paper-ids, and proposed content. Promotion itself requires an explicit user action via `query` + promote or a future `/academic-wiki:wiki promote <candidate-id>` command.
9. **Index update**: sectioned by `field/*` tag.
10. Append to `log.md`: `## [YYYY-MM-DD] compile | N paper pages created/updated`.
11. Commit: `compile: <summary>`.
12. Release lock.

## Query Rules

Answers using the wiki; files the answer.

1. Find relevant pages: qmd if installed, else `index.md` + ripgrep.
2. Read relevant pages; follow one level of wikilinks if targets look relevant.
3. Synthesize answer with `[[wikilinks]]` as citations.
    - Default: prose.
    - If question contains "compare" / "table": markdown table.
    - If question contains "slides": Marp markdown.
4. File answer to `wiki/queries/<slug>.md` (mandatory, no prompt).
5. Prompt: `"Promote to a first-class page? If yes, which type: concept / method / open-problem / claim / result?"` If promoted, move to appropriate subdirectory with appropriate frontmatter schema.
6. Append to `log.md`; commit: `query: <slug>` (and `promote: <slug> to <type>` if promoted).

## Lint Rules

Audits wiki health via `scripts/lint-wiki.py` + LLM suggestions.

**Deterministic checks** (Python, no LLM):

- **Dead links** (`[[foo]]` with no `foo.md`): flagged with context (the file and line where the link appears); not auto-stubbed. Deterministic code cannot infer the target's entity type from the wikilink alone. Stubbing is deferred to an optional LLM pass (`lint --fix-dead-links`) that reads the usage context and creates an appropriate-type stub.
- **Alias resolution**: before flagging a dead link as dead, check every existing page's `aliases:` frontmatter; if the dead link matches an alias, suggest rewriting to the canonical slug.
- **Orphan pages** (no inbound links): list, suggest where to add inbound links.
- **Missing `field/*` tag** on any paper / concept / method / open-problem / claim / result.
- **Missing frontmatter fields** per entity-type schema (uses §3 definitions).
- **Stale pages**: (a) any page with `status: stale` whose `updated:` is >90 days old; (b) any `concept` or `method` page whose `updated:` is >180 days old regardless of status.
- **Missing "Counter-Arguments and Gaps"** on concept / method pages.
- **Contradictions** (`[!WARNING]` markers): list.
- **Invalid `cites:` keys** (no matching paper page `paper-id`): flag as candidate new ingests.
- **Missing BibTeX** (paper page has no corresponding `raw/bib/<paper-id>.bib` or the bib has `bib-incomplete: true`).
- **Index drift** (`wiki/index.md` vs actual files).
- **Extract integrity**: paper page exists but `raw/extracts/<paper-id>.md` is missing, or the extract's `extract-status: failed`.
- **Version drift**: paper page's `identifiers.arxiv-version` differs from the latest entry in the versions manifest (a newer version has been ingested but the paper page hasn't been updated).

**LLM suggestions** (optional pass, `lint --with-suggestions`): 3–5 questions the wiki can't yet answer well, 2–3 sources that would strengthen gaps.

**Optional fix passes** (each opt-in, each separate):
- `lint --fix-dead-links`: LLM creates stubs for flagged dead links using usage context to choose entity type.
- `lint --suggest-backlinks`: LLM identifies pages that *should* link to new pages but don't, and proposes edits (does not apply silently; produces a diff for user review).

Save report to `outputs/reports/YYYY-MM-DD-lint.md`; append to `log.md`; commit.

## Export-BibTeX Rules

Generates a consolidated `.bib` from a subset of paper pages.

**Selectors** (≥1 of the first six required; combinable with AND semantics):

- `--project <slug>` — papers tagged `project/<slug>`.
- `--field <slug>` — papers tagged `field/<slug>`.
- `--tag <tag>` — full tag including prefix.
- `--query <text>` — hybrid search over paper pages.
- `--keys <key1,key2,...>` — explicit list.
- `--since YYYY-MM-DD` — include only papers whose `created:` frontmatter (first-ingest date) is ≥ this date.
- `--label <string>` — optional override for the output filename label.

**Label resolution** (for the output filename):

1. If user passed `--label <string>`, use it verbatim. (Add `--label` to the selector list.)
2. Else: use the first non-empty selector value in this fixed priority order — `project`, `field`, `tag`, `query`, `keys[0]`, `since` — slugified.
3. Example: `export-bibtex --field wireless-comms --since 2024-01-01` → `outputs/bib/2026-04-16-wireless-comms.bib`.

**Pipeline**:

1. Resolve selectors → list of paper pages (AND semantics across multiple selectors).
2. Concatenate `raw/bib/<paper-id>.bib` contents into `outputs/bib/YYYY-MM-DD-<label>.bib`.
3. Report: `N papers exported. M have bib-incomplete flag (listed below).`
4. Append to `log.md`; commit: `export: <label> (<N> papers)`.

## Snapshot Rules

Tags the wiki state for reproducibility. Operates on the wiki's own nested git repo (§2), so the snapshot captures only wiki state — not unrelated Obsidian vault changes.

1. Acquire `{{NAME}}/.lock`.
2. Precondition: `git -C <wiki-path> status --porcelain` must be empty (no unstaged changes). If not, warn with the list of uncommitted files and abort; the user commits pending changes first (they were most likely just made during a prior operation and should already be committed, so this is defensive).
3. `git -C <wiki-path> tag snapshot/<label>` at current HEAD. Tag name is namespaced under `snapshot/` to keep the tag space tidy.
4. Append to `log.md`: `## [YYYY-MM-DD] snapshot | <label>` with SHA.
5. Release lock.
6. Print: `Tagged as snapshot/<label> at <SHA>. Revisit with: git -C <wiki-path> checkout snapshot/<label>`.

## Search Strategy

Single `find_pages(query) → list[SearchHit]` abstraction with multiple backends. The return type is richer than a path to let backends contribute ranking and snippet information.

```python
# Conceptual shape (the Python lint/export helpers may use this; the SKILL.md itself describes the contract informally)
class SearchHit:
    path: str           # relative to wiki root (e.g., "wiki/papers/vaswani2017attention.md")
    score: float        # backend-specific; higher is better; normalized to [0, 1] where possible
    snippet: str        # short matching context, if backend supports it; else empty
    backend: str        # "index+ripgrep" | "qmd" | "mcp:<name>"
```

Callers (query, lint, export-bibtex `--query`) use `path` to read the page, `score` to rank, `snippet` to show context. Backends that don't support `score` or `snippet` return sentinel values (`score=1.0`, `snippet=""`) rather than failing.

### Phase 1 — index.md + ripgrep (default, no dependencies)

LLM reads `wiki/index.md` first to identify candidate matches by title/description, then uses ripgrep for content matching. Returns hits with `score=1.0` and a ripgrep-line `snippet`. Realistic for up to ~100 paper pages plus associated concept/method/etc. pages — beyond that, title-based matching in `index.md` starts missing candidates and ripgrep-across-everything gets noisy.

### Phase 2 — qmd (optional, auto-installed)

If `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd` exists and is executable, use qmd's hybrid BM25 + vector search via `qmd query "<question>" --collection <wiki-name>`. Returns hits with qmd's own `score` and surrounding snippet. Falls back to Phase 1 if qmd crashes, the collection is corrupt, or qmd returns zero hits.

## Lockfile Semantics

Mutating commands (`ingest`, `compile`, `query` with promotion, `lint --fix-*`, `export-bibtex`, `snapshot`, `remove`) take an advisory `{{NAME}}/.lock` at the start and release at the end. The lockfile contains `<pid>:<iso-timestamp>:<op>`.

- Acquiring a held lock: fail fast with `Another operation is in progress: <op> started at <timestamp> by pid <pid>`. User retries after the other op completes.
- Stale lock (holding pid is gone): treat as released. Log a warning and take the lock.
- Any command that panics between acquire and release leaves the lock; stale-pid detection recovers on the next attempt.

Read-only commands (`query` without promotion, `lint` without fix passes) do not take the lock.

## Remove Rules

Deletes a wiki and its nested git repo after confirmation.

1. Acquire `{{NAME}}/.lock` inside `<wiki-path>`.
2. Verify target exists.
3. Confirm: `"This will permanently delete '<name>' AND its git history at <wiki-path>. Proceed? (y/n)"`.
4. Remove qmd collection if present: `qmd collection remove <name>`.
5. Remove the directory entirely: `rm -rf <wiki-path>` (the nested `.git/` goes with it).
6. If the Obsidian vault is itself a git repo, commit the removal so the vault's git knows the directory is gone: `git -C ~/ObsidianVault commit -am "remove: <name> wiki"` (no-op if vault isn't a git repo).

Note: the lock is released by the directory being gone.

## Error Catalog

| Situation | Action |
|---|---|
| **Lockfile held** | Fail fast (see Lockfile Semantics). |
| **Lockfile stale** (holding pid gone) | Warn, take the lock, continue. |
| **No active wiki found** | List candidates in `~/ObsidianVault/03-Resources/*/wiki`. Default to `academic/` if present; else prompt. |
| **Duplicate source (`source-sha` match)** | Skip ingest; print the existing `paper-id`. |
| **Duplicate paper (identifier match, different source-sha)** | Treat as new version of an existing paper; reuse `paper-id`, update `identifiers:`, store new source under the same id with `source-version:` distinguishing. |
| **PDF has no extractable text** | Route to `ocr-papers-to-latex` with OCR mode; if still fails, save PDF as-is, set `extract-status: failed`, warn, don't block. |
| **Metadata extraction fails** | Fallback `paper-id` = `unknown<YYYY><filenameslug>`; set `metadata-incomplete: true`; lint surfaces. |
| **arXiv/DOI API failure** | Retry once with backoff. If still failing, log error; suggest manual ingest. |
| **Paper-id collision** (different paper wants the same id) | Append numeric suffix `2`, `3`, ... (no separator); never overwrite. |
| **BibTeX missing** | Stub minimal `@misc`; set `bib-incomplete: true`. |
| **Git commit fails** | Warn with git output; do not retry; do not use `--no-verify`. User resolves manually. Release lock before surfacing the error. |
| **qmd crashes / corrupt index** | Fall back to Phase 1 search for that operation; warn once per session. |
| **Extract exists, paper page missing** | Treat as uncompiled; next `compile` picks up. |
| **Paper page exists, extract missing** | Lint warning: re-run ingest on the source. |
| **Invalid `cites:` key** | Lint: "candidate new ingests"; do not auto-ingest. |
| **`compile` targets non-existent paper-id** | Abort: `No extract found for <paper-id>. Did you run wiki ingest first?` |
| **Snapshot precondition fails** (uncommitted changes) | Abort with a list of uncommitted files. User commits and retries. |
| **Dead wikilink** | Flag with context in lint; do not auto-stub. Use `lint --fix-dead-links` for an LLM-assisted stub pass. |
| **Version drift** (newer version ingested but paper page not updated) | Lint warning: paper page `identifiers.arxiv-version` behind latest version in `raw/extracts/<paper-id>.versions.yml`. |
"""
