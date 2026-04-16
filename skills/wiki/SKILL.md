---
name: wiki
description: >-
  Academic Wiki — persistent, compounding knowledge base for academic papers inside
  an Obsidian vault. Use when the user says "/academic-wiki:wiki", "wiki init",
  "wiki ingest", "wiki compile", "wiki query", "wiki lint", "wiki export-bibtex",
  "wiki snapshot", or asks about managing an academic knowledge base wiki.
argument-hint: init <name> | ingest <path|id|url> | compile [<paper-id>] [--paper-only] | query <question> | lint | export-bibtex <selectors> | snapshot <label> | remove <name>
---

# Academic Wiki

Persistent, compounding knowledge base for academic papers inside an Obsidian vault. Design spec: `docs/superpowers/specs/2026-04-16-academic-wiki-design.md`.

## Active Wiki Detection

Walk up from `cwd` looking for a directory with both `CLAUDE.md` and a `wiki/` subfolder (via `academic_wiki_lib.wiki_paths.find_active_wiki`). If none found, list `~/ObsidianVault/03-Resources/*/wiki` via `academic_wiki_lib.wiki_paths.list_wikis` and prompt. Default to `academic/` if present.

## Helper invocation

All Python helpers live at `${CLAUDE_PLUGIN_ROOT}/scripts/academic_wiki_lib/`. Invoke via:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c "from academic_wiki_lib import <module>; ..."
```

For the user's local setup, `~/.venv/bin/python` should be used if present (the system Python may lack pyyaml). Prefer `~/.venv/bin/python` when available; fall back to `python3`.

CLI entry points (used in Wave 3+):
- `${CLAUDE_PLUGIN_ROOT}/scripts/lint-wiki.py`
- `${CLAUDE_PLUGIN_ROOT}/scripts/bibtex-export.py`

## `init [<name>]`

Default name: `academic`.

### Setup variables

Before running the steps below, set these shell variables and use them consistently (always quoted):

    NAME="<name>"                      # the wiki name (default "academic")
    WIKI_ROOT="$HOME/ObsidianVault/03-Resources/$NAME"

Use `"$NAME"` and `"$WIKI_ROOT"` in all subsequent shell commands to handle names with spaces or special characters safely.

1. Resolve path: `"$WIKI_ROOT"`. Abort if it already exists; suggest `/academic-wiki:wiki remove <name>` first.
2. Create the 16-subdirectory tree:
    ```bash
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c \
      "from academic_wiki_lib.templates import all_subdirs; import os, sys; \
       base=sys.argv[1]; \
       [os.makedirs(os.path.join(base, d), exist_ok=True) for d in all_subdirs()]" \
      -- "$WIKI_ROOT"
    ```
3. Initialize the wiki's own git repo: `git -C "$WIKI_ROOT" init`
4. Write `CLAUDE.md`:
    ```bash
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c \
      "from academic_wiki_lib.templates import claude_md; import sys; \
       sys.stdout.write(claude_md(sys.argv[1]))" \
      -- "$NAME" > "$WIKI_ROOT/CLAUDE.md"
    ```
5. Write `wiki/index.md`, `log.md`, `.gitignore`, `qmd.yml`:
    ```bash
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -c \
      "from academic_wiki_lib.templates import INDEX_MD; import sys; \
       sys.stdout.write(INDEX_MD.format(name=sys.argv[1]))" \
      -- "$NAME" > "$WIKI_ROOT/wiki/index.md"
    # Similarly for LOG_MD, GITIGNORE, qmd_yml(NAME)
    ```
6. Update the Obsidian vault's `.gitignore` (if `~/ObsidianVault/.git` exists) to exclude `03-Resources/"$NAME"/`:
    ```bash
    if [[ -d "$HOME/ObsidianVault/.git" ]]; then
        LINE="03-Resources/$NAME/"
        GITIGNORE="$HOME/ObsidianVault/.gitignore"
        touch "$GITIGNORE"
        grep -Fxq "$LINE" "$GITIGNORE" || echo "$LINE" >> "$GITIGNORE"
    else
        echo "Note: ~/ObsidianVault is not a git repo; skipped vault .gitignore update."
    fi
    ```
7. Initial commit inside the wiki's own repo:
    ```bash
    git -C "$WIKI_ROOT" add .
    git -C "$WIKI_ROOT" -c user.email=noreply@academic-wiki.local -c user.name="academic-wiki" commit -m "init: $NAME wiki"
    ```
    (Actual user.name/user.email should come from the user's global git config; use `-c` only as fallback if they're not configured.)
8. If qmd is available at `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd`:
    ```bash
    QMD="${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd"
    if [[ -x "$QMD" ]]; then
        env -u BUN_INSTALL "$QMD" collection add "$WIKI_ROOT/wiki" --name "$NAME"
        env -u BUN_INSTALL "$QMD" embed --collection "$NAME"
    fi
    ```
9. Print Web Clipper + Zotero setup hints:
    ```
    Obsidian Web Clipper setup:
    1. Install: https://obsidian.md/clipper
    2. Destination folder: 03-Resources/$NAME/raw/papers
    3. Filename: {{date:YYYY-MM-DD}}-{{title}}
    4. After clipping, run: /academic-wiki:wiki ingest <path>

    Zotero BibTeX export (optional): File → Export → BibTeX → save to raw/bib/
    ```

## `ingest <path|id|url>`

Save a source to `raw/` and assign a canonical `paper-id`. Does NOT create wiki pages — use `compile` for that.

### Setup variables

Detect the active wiki (via `academic_wiki_lib.wiki_paths.find_active_wiki` from cwd, or default to `~/ObsidianVault/03-Resources/academic`):

    PY=~/.venv/bin/python  # fall back to python3 if not present
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    WIKI_ROOT="<active-wiki-path>"

### Steps

1. **Acquire lockfile:**
    ```bash
    "$PY" -c "
    import sys; sys.path.insert(0, '${PYTHONPATH}')
    from academic_wiki_lib.lockfile import acquire
    acquire('${WIKI_ROOT}/.lock', op='ingest')
    "
    ```
    If this fails with `LockHeld`, another operation is in progress — print the error and exit.

    Also set a trap so the lock is released even if a later step fails:
    ```bash
    trap '"$PY" -c "import sys; sys.path.insert(0, \"${PYTHONPATH}\"); from academic_wiki_lib.lockfile import release; release(\"${WIKI_ROOT}/.lock\")"' EXIT
    ```

2. **Route input:** see `references/ingestion-routing.md`. Given the user's input string:
   - Match against each pattern in order; first match wins.
   - Invoke the appropriate handler (MCP tool, skill, or direct file operation).
   - The handler returns: raw bytes/text + metadata (title, authors, year, identifiers, optional BibTeX).

3. **Compute source-sha:**
    ```bash
    "$PY" -c "
    import sys; sys.path.insert(0, '${PYTHONPATH}')
    from academic_wiki_lib.source_sha import file_sha256
    print(file_sha256('<raw-source-path>'))
    "
    ```

4. **Dedup pass 1 (byte-level):** scan existing `raw/extracts/*.md` frontmatter for a matching `source-sha` field. If found, release lock, print `This exact source was already ingested as <existing-paper-id>. Skipping.` and exit.

5. **Extract metadata** from handler output + source content:
   - First-author last name (ASCII-folded, lowercased: `García` → `garcia`)
   - 4-digit publication year
   - Title's first meaningful word (lowercased; skip stop words `a`/`an`/`the` and pure numerals)
   - Identifiers dict: `{doi, arxiv, arxiv-version, url}` — populate whichever are known

6. **Dedup pass 2 (identifier-level):**
    ```bash
    "$PY" -c "
    import sys, json; sys.path.insert(0, '${PYTHONPATH}')
    from academic_wiki_lib.paper_id import find_existing_paper_by_identifiers
    identifiers = {'doi': 'X', 'arxiv': 'Y'}  # as extracted
    result = find_existing_paper_by_identifiers('${WIKI_ROOT}', identifiers)
    print(result or '')
    "
    ```
    Compare extracted identifiers against every existing paper page's `identifiers:`. If any non-empty identifier matches (`doi`, `arxiv` ignoring version, `url`), the paper already exists:
    - a. Load the existing `paper-id`.
    - b. **MERGE identifiers:** read the existing paper page's `identifiers:` frontmatter; add any identifiers from the incoming source that weren't already set. Write back the updated `identifiers:` to the paper page. Example: existing has `{arxiv: "1706.03762"}`, incoming provides `{doi: "10.xxx/yyy"}` — after merge, existing page has `{arxiv: "1706.03762", doi: "10.xxx/yyy"}`.
    - c. Compare the incoming `source-version` against the existing one. If different → proceed to step 8 (version handling). If same or unknown → skip saving a new version (the paper's already here with this source), release lock, log `ingest: deduped <paper-id> (merged identifiers)`, and exit.

    If no identifier matches, the paper does not yet exist — proceed to step 7.

7. **Generate paper-id** (new paper):
    ```bash
    "$PY" -c "
    import sys; sys.path.insert(0, '${PYTHONPATH}')
    from academic_wiki_lib.paper_id import generate_paper_id, resolve_collision
    pid = generate_paper_id('Lastname', 2017, 'Title Words')
    pid = resolve_collision('${WIKI_ROOT}', pid)
    print(pid)
    "
    ```
    Format: `<lastname>-<year>-<firstword>`. If already taken by a different paper (different identifiers), append `-2`, `-3`, ... until unique.

8. **Handle versions** (if dedup pass 2 matched an existing paper): if the incoming `source-version` differs from the existing paper's `source-version`, this is a new version of the same paper:
   - Save the new source file and extract with the same `paper-id` basename, with `source-version: arxiv-v5` (or appropriate version) in the extract frontmatter.
   - Append to a per-paper manifest: `raw/extracts/<paper-id>.versions.yml` listing every version ingested with its `source-sha`, `extracted-at`, and `source-path`.
   - Update `wiki/papers/<paper-id>.md` `identifiers.arxiv-version:` to the most recent version.

9. **Metadata-extraction failure fallback** — trigger if ANY of:
   - First author could not be identified (no author mentioned, or only "Anonymous" etc.)
   - Year could not be determined as a 4-digit number in the publication range (1900–current year +1)
   - Title's first meaningful word cannot be extracted (title is missing or consists only of stop words)

   If the failure is partial (e.g., year known but author unknown), still use the fallback — do NOT synthesize a partial `paper-id`.

   Fallback action:
   - `paper-id` = `unknown-<current-year>-<filename-slug>`
   - Set `metadata-incomplete: true` in the extract frontmatter
   - Include whatever metadata WAS extractable in the extract frontmatter (don't drop year if that was the only field found)
   - Lint will surface this for manual cleanup later

10. **Save files** with `<paper-id>` as the consistent basename:
    - `raw/papers/<paper-id>.pdf` (or `.html`, `.md`, `.tex` depending on source type)
    - `raw/extracts/<paper-id>.md` — the LLM-readable extract with full frontmatter (§3.7)
    - `raw/bib/<paper-id>.bib` — either real or stubbed
    - `raw/figures/<paper-id>/` — if figures were extracted; else create empty directory

11. **Write extract frontmatter** per spec §3.7. Required fields: `paper-id`, `source-path`, `source-sha`, `source-version`, `source-type`, `source-url`, `extractor`, `extractor-version`, `extracted-at` (ISO-8601 UTC), `ocr-used`, `extract-status`, `extract-warnings`.

12. **BibTeX:** if the handler provided BibTeX (arXiv/DOI/publisher handlers usually can), save it verbatim to `raw/bib/<paper-id>.bib`. Otherwise stub a minimal `@misc` entry from the extracted metadata, with a comment `% bib-incomplete: true` at the top (lint will flag it). The BibTeX `@key` field uses `citation-key` (BibTeX-native style, no hyphens: `vaswani2017attention`), not `paper-id`.

13. **Append to `log.md`:**
    ```
    ## [YYYY-MM-DD] ingest | <paper-id>
    New paper ingested from <source>.
    ```
    Variants:
    - New version: `New version <source-version> of existing paper <paper-id>.`
    - Deduped: handled at step 4 (wouldn't reach this step).

14. **Commit inside the wiki's own git repo:**
    ```bash
    git -C "$WIKI_ROOT" add .
    git -C "$WIKI_ROOT" commit -m "ingest: <paper-id>"
    ```
    Commit message variants:
    - `ingest: <paper-id> (new version v5)` — if step 8 was reached
    - `ingest: deduped <paper-id>` — if step 4 matched (though execution exits there)

15. **Release lockfile** (the EXIT trap from step 1 handles this automatically; also call explicitly after commit):
    ```bash
    "$PY" -c "
    import sys; sys.path.insert(0, '${PYTHONPATH}')
    from academic_wiki_lib.lockfile import release
    release('${WIKI_ROOT}/.lock')
    "
    ```

16. **Print confirmation:**
    ```
    Source saved with paper-id <paper-id>. Run /academic-wiki:wiki compile <paper-id> to integrate into the wiki.
    ```

### Error recovery

If any step 2–14 fails after the lock is acquired, the skill MUST still release the lock. The `trap` set in step 1 ensures this:

```bash
trap '"$PY" -c "import sys; sys.path.insert(0, \"${PYTHONPATH}\"); from academic_wiki_lib.lockfile import release; release(\"${WIKI_ROOT}/.lock\")"' EXIT
```

This fires on any exit (normal or error). The explicit release in step 15 is not strictly required when the trap is set, but is included for clarity. If the trap cannot be set (e.g., non-bash shell), wrap steps 2–14 in a try/finally in Python and call release in the finally block.

## `compile [<paper-id>] [--paper-only]`

Wave 1 ships **paper-only tier** as default. Creates/updates `wiki/papers/<paper-id>.md` from `raw/extracts/<paper-id>.md`. Does NOT do entity extraction, cross-paper synthesis, or backlink audit — those arrive in Wave 2.

For detailed behavior see `references/compilation-guide.md`.

### Setup variables

    PY=~/.venv/bin/python
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    WIKI_ROOT="<active-wiki-path>"

### Steps (paper-only tier)

1. **Acquire lockfile** (op=`compile`):
    ```bash
    "$PY" -c "
    import sys; sys.path.insert(0, '$PYTHONPATH')
    from academic_wiki_lib.lockfile import acquire
    acquire('$WIKI_ROOT/.lock', op='compile')
    "
    trap '"$PY" -c "import sys; sys.path.insert(0, \"'$PYTHONPATH'\"); from academic_wiki_lib.lockfile import release; release(\"'$WIKI_ROOT'/.lock\")"' EXIT
    ```

2. **Identify sources to compile:**
   - If `<paper-id>` given: just that one.
   - Else: list `raw/extracts/*.md` (excluding `*.versions.yml`). For each, check whether `wiki/papers/<paper-id>.md` exists; if it does, compare the extract's `extracted-at` to the paper page's `updated:` — only re-compile if the extract is newer (source changed since last compile). Compile all sources that are new or updated.
   - If nothing to compile: print `All sources already compiled. Nothing to do.` Release lock, exit.

3. **For each source:**
    a. Read `raw/extracts/<paper-id>.md` via `read_frontmatter`. Keep the body (the actual paper text/LaTeX).
    b. Read `raw/notes/<paper-id>.md` if it exists.
    c. Check if `wiki/papers/<paper-id>.md` already exists (update case) — if yes, read it and apply the update conflict policy (§3.6) during merge.
    d. LLM generates body content: Metadata / Summary / Key Contributions / Methods / Results / Claims / User Notes / See Also sections.
    e. LLM extracts `references-raw: [...]` from the bibliography section of the extract.
    f. LLM infers `field/*`, `subfield/*`, `method/*` tags from content. `year/<YYYY>` and `venue/<slug>` from frontmatter.
    g. Populate `authors:` as list of `{slug: <author-slug>, name: <human-name>}` objects. Generate each slug via `academic_wiki_lib.slug.make_slug`.
    h. Write `wiki/papers/<paper-id>.md` via `academic_wiki_lib.frontmatter.write_frontmatter`.

4. **Update `wiki/index.md`:** append under a `## Uncategorized` heading (field tagging kicks in properly in Wave 2). Format: `- [[<paper-id>]] — <title> (YYYY-MM-DD)`. Avoid duplicates (check if the line already exists).

5. **Append to `log.md`:** `## [YYYY-MM-DD] compile | N paper pages created/updated` with a body line listing the paper-ids.

6. **Commit inside the wiki's own repo:**
    ```bash
    git -C "$WIKI_ROOT" add .
    git -C "$WIKI_ROOT" commit -m "compile: paper-only <N> papers: <first-paper-id>, ..."
    ```

7. **Release lock** (trap handles this on exit).

### When updating an existing paper page

Apply spec §3.6: preserve prior claims, append new evidence, flag contradictions with `[!WARNING]` callouts, bump `updated:`, never replace without provenance.

### Full tier (Wave 2 — default after Wave 1 is stable; Wave 1 tier remains available via `--paper-only`)

All paper-only tier steps, PLUS:

1. **Entity extraction:** after the paper page is written, scan the extract body for mentions of concepts, methods, and open problems. For each identified entity:
    a. Generate a slug via `academic_wiki_lib.slug.make_slug(<entity-name>)`.
    b. Check if `wiki/<entity-type>s/<slug>.md` exists (where entity-type is `concept`, `method`, or `open-problem`).
    c. If yes: apply §3.6 update conflict policy. Append the current paper-id to `sources:`. Merge any new information from the paper's coverage into the entity page's body. Flag contradictions with `[!WARNING]` callouts. Bump `updated:`.
    d. If no: create using the appropriate §3 template. Populate `sources: [<paper-id>]`, `tags: [field/..., subfield/...]` (inherit from the paper's tags), and `status:` set per the entity type's allowed values:
       - concept: `active`
       - method: `active`
       - open-problem: `open` (default; override to `resolved` only if the paper explicitly provides a resolution)
       - result: `preliminary` (default; promote to `replicated`/`contested` later via cross-paper candidate detection)
       - claim: `established` (default; promote to `contested`/`fringe` only if other papers push back)
    e. Add `[[wikilinks]]` to the new entity pages in the paper's Methods/Claims/Summary sections as appropriate.

2. **`cites:` resolution:** for each entry in the paper's `references-raw: [...]`:
    a. Attempt to fuzzy-match the reference against existing paper pages by title + first-author + year (LLM judgment; loose string match + semantic verification).
    b. If a match is found, append its paper-id to `cites: [...]`.
    c. Unmatched entries stay in `references-raw:` only and surface in lint's "candidate new ingests" list.

3. **Backlink audit with ≥2-word slug allowlist** — prevent over-linking of common words:
    a. For each newly-created entity-page slug, run:
        ```bash
        rg -l -n --fixed-strings "<slug-with-hyphens-replaced-by-space>" "$WIKI_ROOT/wiki/"
        ```
    b. For each matching page, only insert `[[<slug>]]` if EITHER:
       - The slug is ≥2 hyphen-separated words (e.g., `attention-mechanism`, `rate-splitting-multiple-access`), OR
       - The match appears in a noun phrase that the LLM recognizes as a proper named entity (e.g., in prose like "the Transformer architecture" where `transformer` is a single-word slug but a proper name).
    c. Skip insertion for single-word slugs like `attention`, `method`, `training` unless rule 3b.2 applies.
    d. Commit backlink additions together with the entity pages in the same git commit as the compile.

4. **Cross-paper candidate detection** (per `references/promotion-rules.md`): for each claim/result drafted in the paper page, search for semantically equivalent claims/results in other paper pages. When ≥1 equivalent found, append a candidate entry to `outputs/reports/YYYY-MM-DD-promotion-candidates.md`. **Do NOT silently promote** — the user reviews and accepts via query or future `promote` command.

5. **Index update (replacing paper-only Uncategorized):** rewrite `wiki/index.md` with sections by `field/*` tag. Each paper gets listed under its primary field (if multiple, listed under each).

    ```markdown
    # academic Wiki Index

    Last updated: YYYY-MM-DD

    ## field/wireless-comms
    - [[vaswani-2017-attention]] — Attention Is All You Need (2026-04-16)
    - [[chen-2023-5g]] — 5G Networks Survey (2026-04-17)

    ## field/nlp
    - [[vaswani-2017-attention]] — Attention Is All You Need (2026-04-16)

    ## concepts
    - [[attention-mechanism]] — The attention mechanism (2026-04-16)

    ## methods
    - [[rsma]] — Rate-Splitting Multiple Access (2026-04-17)
    ```

6. Log + commit + qmd re-embed per paper-only flow (unchanged).

## `query <question>`

Answer a question against the wiki's paper pages (and, in Wave 2+, concept/method/etc. pages). Files the answer for future reuse.

### Setup variables

    PY=~/.venv/bin/python
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    WIKI_ROOT="<active-wiki-path>"
    QMD="${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd"

Query is mostly read-only. It only takes the lock if the user accepts the promotion prompt at the end.

### Steps

1. **Determine search backend:**
   - If `qmd` exists and is executable AND a qmd collection for this wiki exists → Phase 2 (qmd).
   - Otherwise → Phase 1 (index.md + ripgrep).

2. **Phase 1 search (index.md + ripgrep):**
   - Read `wiki/index.md` in full. Identify candidate paper-ids by matching query keywords against entry titles/descriptions (LLM judgment — loose word match on meaningful nouns).
   - Run ripgrep for the question's meaningful nouns (skip stop words) against `wiki/papers/*.md`:
        ```bash
        rg -l -i -e "<noun1>" -e "<noun2>" "$WIKI_ROOT/wiki/papers/"
        ```
     Collect the matching paper-ids.
   - Union of index-matches and ripgrep-matches = candidates (deduplicated).
   - Each hit = `{path, score: 1.0, snippet: ripgrep_first_match_line, backend: "index+ripgrep"}`.

3. **Phase 2 search (qmd, only when available):**
    ```bash
    env -u BUN_INSTALL "$QMD" query "<question>" --collection <wiki-name> --json
    ```
   Parse JSON output for path/score/snippet per hit.

4. **Read all candidate paper pages.** Follow one level of wikilinks if the linked target has frontmatter `type: paper` (or any existing wiki page in Wave 1 — concept/method/etc. don't exist yet).

5. **Synthesize answer:**
   - Default: **prose** with inline `[[paper-id]]` wikilinks as citations. Every factual claim must be attributed.
   - If the question contains "compare" or "table": markdown table with paper-ids in cells.
   - If the question contains "slides": Marp markdown with `marp: true` frontmatter; save as `.md` that can be rendered via `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/marp`.

6. **File the answer to `wiki/queries/<slug>.md`** (mandatory, no prompt). Use this frontmatter:
    ```yaml
    ---
    type: query-output
    question: "<original question>"
    status: filed
    created: YYYY-MM-DD
    updated: YYYY-MM-DD
    sources: [<paper-id-1>, <paper-id-2>, ...]    # all cited paper-ids
    tags: [field/..., ...]                         # union of tags from sources
    ---
    ```
    Slug: `academic_wiki_lib.slug.make_slug(<question>)` (truncated at 60 chars automatically).

    Acquire the lockfile JUST BEFORE writing this file (query is mostly read-only; only the write needs a lock).

7. **Prompt for promotion:**
    ```
    Promote this answer to a first-class page? Type one of:
      - "concept", "method", "open-problem", "claim", "result" — promote as that type
      - "no" — keep only in queries/
    ```

    If the user accepts:
    - Move the file from `wiki/queries/<slug>.md` to `wiki/<type>s/<slug>.md` (e.g., `wiki/concepts/<slug>.md`).
    - Update frontmatter: `type: <chosen-type>`, `status: promoted` (for query-output, then convert to the target entity's schema), `sources:` stays.
    - Expand the file into the target entity's schema (§3.1-3.3 for that type). The LLM rewrites the body to match the target template (e.g., for `concept`: `Definition` / `Details` / `See Also` / `Counter-Arguments and Gaps`).

8. **Append to `log.md`:** `## [YYYY-MM-DD] query | <slug>`. If promoted: also `## [YYYY-MM-DD] promote | <slug> to <type>`.

9. **Commit inside the wiki's own repo** if anything was written:
    ```bash
    git -C "$WIKI_ROOT" add .
    git -C "$WIKI_ROOT" commit -m "query: <slug>"
    ```
    Use `promote: <slug> to <type>` if promoted instead.

10. **Release lockfile** (if acquired in step 6).

### Search ranking notes

- Phase 1 returns hits with uniform `score: 1.0` — no real ranking, LLM uses order of reading.
- Phase 2 (qmd) returns hits with qmd's BM25+vector scores.
- Controller/LLM should read the top candidates first; stop adding more when confident there's enough evidence for a thorough answer. Typical: 5-15 paper pages per query.

### Wave 2+ extensions

Once Wave 2 compile creates concept/method/open-problem pages, query extends:
- Candidate set includes non-paper entity pages.
- Wikilink-following can cross into entity pages.
- Promotion prompt offers all entity types (already listed above).

## `lint [--fix-dead-links] [--suggest-backlinks] [--with-suggestions]`

<Wave 3 fills this in.>

## `export-bibtex <selectors>`

<Wave 3 fills this in.>

## `snapshot <label>`

<Wave 3 fills this in.>

## `remove <name>`

<Wave 4 fills this in.>
