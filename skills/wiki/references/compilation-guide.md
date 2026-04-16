# Compilation Guide

## Paper-only tier (Wave 1 default)

The paper-only tier is the safe starting point. It produces paper pages from raw extracts WITHOUT:
- Creating entity pages (concept/method/open-problem)
- Running cross-paper synthesis
- Resolving `cites:` (stays empty; `references-raw:` holds verbatim bibliography)
- Running backlink audit

### Per-source steps

For each paper-id to compile:

1. Read `raw/extracts/<paper-id>.md` via `academic_wiki_lib.frontmatter.read_frontmatter`. The frontmatter gives you `paper-id`, `source-path`, `source-sha`, `source-version`, `source-url`, and extractor metadata.

2. Read `raw/notes/<paper-id>.md` if it exists. This file is user-authored; treat as immutable source.

3. Determine paper `status:` — set to `read` if user notes are present and non-trivial (>200 chars), else `skimmed`. LLM may override based on content depth.

4. Write (or update) `wiki/papers/<paper-id>.md` with:
    - Full frontmatter per §3.1: `paper-id`, `citation-key` (derived BibTeX-style from author+year+firstword), `type: paper`, `status`, `created` (today if new), `updated` (today), `publication-date` (if known), `title`, `authors` (list of `{slug, name}` objects), `year`, `venue`, `identifiers`, `aliases: []`, `source-version`, `bib-file`, `extract`, `notes` (only if `raw/notes/<paper-id>.md` exists), `figures` (only if `raw/figures/<paper-id>/` is non-empty), `references-raw` (list of raw bibliography strings), `cites: []` (empty in Wave 1), `tags`.
    - Body sections: `## Metadata` (inline one-liner: "X et al., YEAR, VENUE. [arXiv|DOI|URL](...) | [PDF](...)"), `## Summary` (LLM-synthesized one-paragraph synopsis), `## Key Contributions` (bullet list), `## Methods` (prose with inline methods), `## Results` (key findings; cross-paper results will be promoted later in Wave 2), `## Claims` (paper's main assertions), `## User Notes` (link-in and summarize `raw/notes/<paper-id>.md` or print `_No user notes filed._`), `## See Also` (links to related wiki pages).

5. Extract bibliography from the extract body and populate `references-raw: [...]` — verbatim strings.

### When updating an existing paper page (re-compile)

Apply spec §3.6 update conflict policy:
- Read existing content; preserve prior claims.
- Append new evidence from the new source.
- Flag any contradictions with `> [!WARNING] Contradiction with [[other-paper-id]]` callouts.
- Bump `updated:` frontmatter to today.

### What NOT to do in paper-only tier (deferred to Wave 2)

- Do NOT create `wiki/concepts/`, `wiki/methods/`, `wiki/open-problems/`, `wiki/claims/`, `wiki/results/` entries.
- Do NOT fuzzy-match claims/results across papers.
- Do NOT resolve `cites:` (leave empty).
- Do NOT run grep-based backlink audit.

Wave 2 lifts these restrictions.

## Full tier (Wave 2)

[Stub — filled in during Wave 2 Task 2.1. Will add entity extraction, cites resolution, backlink audit with ≥2-word allowlist, cross-paper candidate detection (writing to `outputs/reports/YYYY-MM-DD-promotion-candidates.md` — NOT silent auto-promote).]
