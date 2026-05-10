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

Walk up from `cwd` looking for a directory with both `CLAUDE.md` and a `wiki/` subfolder (via `academic_wiki_lib.wiki_paths.find_active_wiki`). If none found, list `~/Documents/Obsidian Vault/03-Resources/*/wiki` via `academic_wiki_lib.wiki_paths.list_wikis` and prompt. Default to `academic/` if present.

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
    WIKI_ROOT="$HOME/Documents/Obsidian Vault/03-Resources/$NAME"

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
6. Update the Obsidian vault's `.gitignore` (if `~/Documents/Obsidian Vault/.git` exists) to exclude `03-Resources/"$NAME"/`:
    ```bash
    VAULT="$HOME/Documents/Obsidian Vault"
    if [[ -d "$VAULT/.git" ]]; then
        LINE="03-Resources/$NAME/"
        GITIGNORE="$VAULT/.gitignore"
        touch "$GITIGNORE"
        grep -Fxq "$LINE" "$GITIGNORE" || echo "$LINE" >> "$GITIGNORE"
    else
        echo "Note: ~/Documents/Obsidian Vault is not a git repo; skipped vault .gitignore update."
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

## `ingest [<path|id|url>]`

Save a source to `raw/` and assign a canonical `paper-id`. Does NOT create wiki pages — use `compile` for that.

### Modes

- **Explicit:** `ingest <path|id|url>` — ingest a single source (file path, directory, arXiv ID, DOI, URL).
- **Batch:** `ingest` with no argument — scan `raw/papers/*/` for unprocessed clipper directories and ingest each.

### Batch scan mode (no argument)

When called with no argument:

1. Walk `raw/papers/*/` for directories containing ≥1 `.md` file.
2. Filter to unprocessed: no `paper-id` in the `.md` frontmatter, OR `paper-id` present but `extract-status` absent/not `complete` (crash recovery).
3. Acquire the lock ONCE before the loop (not per-directory). Set the EXIT trap once.
4. Process each directory sequentially using the clipper flow below. Papers processed earlier in the batch are visible to later dedup scans (their `paper-id` is already written).
5. Release the lock after the loop completes.
6. Print summary: `Ingested N papers from raw/papers/`.

### Clipper directory ingest

When the input is a directory (explicit path or from batch scan) containing `.md` + optional `images/`:

1. Find the `.md` file inside the directory (the clipper writes exactly one).
2. Read the existing frontmatter with `read_frontmatter()` — do NOT overwrite user/clipper fields (`title`, `doi`, `date`, `venue`, etc.).
3. Extract metadata from the frontmatter + body, run the standard metadata pipeline (first-author → year → first-word), generate `paper-id` (new no-hyphen format).
4. Run dedup passes (byte-level + identifier-level) — scoped over both `raw/extracts/` and `raw/papers/*/`.
5. Merge missing fields into the frontmatter and write back with `write_frontmatter()`:
   - `paper-id`
   - `source-sha`
   - `source-type: clipper-md`
   - `source-url` — `https://doi.org/<doi>` if DOI present; else URL from clipper frontmatter if present; else `null`
   - `extracted-at` (ISO-8601 UTC)
   - `extract-status: complete`
   - `extractor` — set to `obsidian-clipper` UNLESS the existing frontmatter already has `extractor: s2-stub` (in which case preserve `s2-stub` so future audits can identify entries that were first cached by an S2 query rather than clipped by the user).
   - `ocr-used: false`
   - `extract-warnings: []`
6. If `images/` subdirectory exists, create a **relative** symlink: `ln -sr "$WIKI_ROOT/raw/papers/<clipper-dir>/images" "$WIKI_ROOT/raw/figures/<paperid>"` (relative so it survives vault relocation).
7. Leave image references (`![[fig1.png]]`) in the body untouched — Obsidian resolves them vault-wide.
8. Stub BibTeX to `raw/bib/<paperid>.bib` as usual.
9. Log + commit.

**Clipper differences from standard ingest:**
- No `raw/extracts/<paperid>.md` is created — the clipper `.md` IS the extract.
- No `raw/papers/<paperid>.*` copy — the clipper directory is the canonical source.
- Figures are symlinked, not copied.

### Setup variables

Detect the active wiki (via `academic_wiki_lib.wiki_paths.find_active_wiki` from cwd, or default to `~/Documents/Obsidian Vault/03-Resources/academic`):

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

4. **Dedup pass 1 (byte-level):** scan BOTH `raw/extracts/*.md` AND `raw/papers/*/` clipper `.md` files for a matching `source-sha` field in frontmatter. If found, release lock, print `This exact source was already ingested as <existing-paper-id>. Skipping.` and exit.

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
    Format: `<lastname><year><firstword>` (no separators). If already taken by a different paper (different identifiers), append `2`, `3`, ... directly (no separator) until unique. `resolve_collision()` scans both `wiki/papers/*.md` filenames AND `paper-id` values in clipper `.md` frontmatter under `raw/papers/*/`.

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
   - `paper-id` = `unknown<currentyear><filenameslug>` (no separators)
   - Set `metadata-incomplete: true` in the extract frontmatter
   - Include whatever metadata WAS extractable in the extract frontmatter (don't drop year if that was the only field found)
   - Lint will surface this for manual cleanup later

10. **Save files** with `<paper-id>` as the consistent basename:
    - `raw/papers/<paper-id>.pdf` (or `.html`, `.md`, `.tex` depending on source type)
    - `raw/extracts/<paper-id>.md` — the LLM-readable extract with full frontmatter (§3.7)
    - `raw/bib/<paper-id>.bib` — either real or stubbed
    - `raw/figures/<paper-id>/` — if figures were extracted; else create empty directory

11. **Write extract frontmatter** per spec §3.7. Required fields: `paper-id`, `source-path`, `source-sha`, `source-version`, `source-type`, `source-url`, `extractor`, `extractor-version`, `extracted-at` (ISO-8601 UTC), `ocr-used`, `extract-status`, `extract-warnings`.

12. **BibTeX:** if the handler provided BibTeX (arXiv/DOI/publisher handlers usually can), save it verbatim to `raw/bib/<paper-id>.bib`. Otherwise stub a minimal `@misc` entry from the extracted metadata, with a comment `% bib-incomplete: true` at the top (lint will flag it). The BibTeX `@key` field uses `paper-id` directly (e.g., `vaswani2017attention`).

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

Default compile runs the full pipeline: paper pages + entity extraction + cites resolution + backlink audit + cross-paper candidate detection + index rebuild. `--paper-only` is an escape hatch that skips entity extraction through cross-paper detection (useful for a fast first pass on a new source). Venue pages under `wiki/venues/<slug>.md` are auto-created or updated for every paper whose extract frontmatter carries a `venue:` field — this happens in both modes.

For detailed behavior see `references/compilation-guide.md`.

### Routing

1. If `<paper-id>` is given: use the sequential path below (unchanged).
2. If no `<paper-id>`:
   a. Check for existing checkpoint via `read_checkpoint()`.
      - If found with `status: in-progress`: enter resume flow (see `references/compilation-guide.md` "Resume flow").
      - If found and stale (>24h): prompt user — resume or start fresh.
   b. If no checkpoint: scan pending papers via `find_all_extracts()` + compare against `wiki/papers/`.
      - If ≤5 pending: use sequential path below.
      - If >5 pending: enter batch mode (see `references/compilation-guide.md` "Batch compile mode").

### Setup variables

    PY=~/.venv/bin/python
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    WIKI_ROOT="<active-wiki-path>"

### Steps

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
   - Call `find_all_extracts(wiki_root)` from `academic_wiki_lib.wiki_paths` — it returns `(paper_id, md_path)` tuples from BOTH `raw/extracts/*.md` and `raw/papers/*/` clipper directories, sorted alphabetically by paper_id.
   - If `<paper-id>` given: filter the list to that one.
   - Else: filter out sources already compiled. A source is "already compiled" if `wiki/papers/<paper-id>.md` exists AND its `updated:` frontmatter is ≥ the extract's `extracted-at`.
   - If nothing to compile: print `All sources already compiled. Nothing to do.` Release lock, exit.

3. **Per-source (all modes):** for each `(paper_id, md_path)` tuple:
    a. Read `md_path` via `read_frontmatter` — use the `md_path` from the tuple, do NOT reconstruct from `paper-id` (clipper extracts live under `raw/papers/<dir>/`, not `raw/extracts/`).
    b. Read `raw/notes/<paper-id>.md` if it exists.
    c. Check if `wiki/papers/<paper-id>.md` already exists (update case) — if yes, apply the update conflict policy (§3.6) during merge.
    d. LLM generates body content: Metadata / Summary / Key Contributions / Methods / Results / Claims / User Notes / See Also sections.
    e. LLM extracts `references-raw: [...]` from the bibliography section of the extract.
    f. LLM infers `field/*`, `subfield/*`, `method/*` tags from the extract body.
       ALWAYS add the deterministic tags from the extract frontmatter:
         - `year/<YYYY>` — from the extract's `year:` or `date:` field (first 4-digit year found).
         - `venue/<slug>` — where `<slug> = academic_wiki_lib.slug.make_slug(<raw-venue-string>)` from the extract's `venue:` field.
       Record the slug (not the raw string) in the paper page's `venue:` frontmatter field.
    g. Populate `authors:` as list of `{slug: <author-slug>, name: <human-name>}` objects. Generate each slug via `academic_wiki_lib.slug.make_slug`.
    h. Write `wiki/papers/<paper-id>.md` via `academic_wiki_lib.frontmatter.write_frontmatter`.
    i. **Venue page upsert** — after writing the paper page, create or update `wiki/venues/<venue-slug>.md`:
       - If the extract has no `venue:` field (missing or empty/whitespace), skip this step entirely.
       - Compute `venue-type = academic_wiki_lib.templates.guess_venue_type(<raw-venue-string>)`.
       - If `wiki/venues/<venue-slug>.md` does not exist: render via `academic_wiki_lib.templates.venue_md_stub(slug=<venue-slug>, name=<raw-venue-string>, venue_type=<venue-type>, paper_ids=[<paper-id>], field_tags=<paper's field/* tags>, today=<YYYY-MM-DD>)` and write the returned string to the file path (plain `open(path, "w").write(...)`).
       - If it exists: read with `academic_wiki_lib.frontmatter.read_frontmatter`, append `<paper-id>` to `papers:` (dedup, preserve order), union `field/*` tags into `tags:` (dedup, preserve order), bump `updated:` to today. Do not change `created:`, `name:`, `venue-type:`, or `slug:` (the user may have corrected them). Write back with `academic_wiki_lib.frontmatter.write_frontmatter`.
       - Runs in ALL modes (default AND `--paper-only`) — venue pages are cheap and belong with the paper write.

4. **Entity extraction** (skipped with `--paper-only`): scan the extract body for mentions of concepts, methods, and open problems. For each identified entity:
    a. Generate a slug via `academic_wiki_lib.slug.make_slug(<entity-name>)`.
    b. Check if `wiki/<entity-type>s/<slug>.md` exists (where entity-type is `concept`, `method`, or `open-problem`).
    c. If yes: apply the update conflict policy (§3.6).
    d. If no: create using the appropriate §3 template. Populate `sources: [<paper-id>]`, `tags:` inherited from the paper's tags, and `status:`:
       - concept: `active`
       - method: `active`
       - open-problem: `open` (override to `resolved` only if the paper explicitly resolves)
       - result: `preliminary`
       - claim: `established`
    e. Add `[[wikilinks]]` to the new entity pages in the paper's Methods/Claims/Summary sections.

5. **`cites:` resolution** (skipped with `--paper-only`): for each entry in the paper's `references-raw: [...]`:
    a. Fuzzy-match against existing paper pages by title + first-author + year.
    b. If matched, append its paper-id to `cites: [...]`.
    c. Unmatched entries stay in `references-raw:` only and surface in lint's "candidate new ingests" list.

6. **Backlink audit with ≥2-word slug allowlist** (skipped with `--paper-only`) — prevents over-linking of common words:
    a. For each newly-created entity-page slug:
        ```bash
        rg -l -n --fixed-strings "<slug-with-hyphens-replaced-by-space>" "$WIKI_ROOT/wiki/"
        ```
    b. Only insert `[[<slug>]]` if EITHER:
       - The slug is ≥2 hyphen-separated words (e.g., `attention-mechanism`), OR
       - The match appears in a noun phrase recognized as a proper named entity.
    c. Skip insertion for single-word slugs like `attention`, `method`, `training` unless rule 6b.2 applies.

7. **Cross-paper candidate detection** (skipped with `--paper-only`, per `references/promotion-rules.md`): for each claim/result drafted in the paper page, search for semantically equivalent claims/results in other paper pages. When ≥1 equivalent found, append a candidate entry to `outputs/reports/YYYY-MM-DD-promotion-candidates.md`. **Do NOT silently promote.**

8. **Update `wiki/index.md`:**
   - Full mode: rewrite with sections by `field/*` tag. Each paper gets listed under its primary field(s).
   - `--paper-only`: append under a `## Uncategorized` heading. Format: `- [[<paper-id>]] — <title> (YYYY-MM-DD)`. Avoid duplicates.

   Example (full mode):
    ```markdown
    # academic Wiki Index

    Last updated: YYYY-MM-DD

    ## field/wireless-comms
    - [[vaswani2017attention]] — Attention Is All You Need (2026-04-16)
    - [[chen20235g]] — 5G Networks Survey (2026-04-17)

    ## field/nlp
    - [[vaswani2017attention]] — Attention Is All You Need (2026-04-16)

    ## concepts
    - [[attention-mechanism]] — The attention mechanism (2026-04-16)

    ## methods
    - [[rsma]] — Rate-Splitting Multiple Access (2026-04-17)
    ```

9. **Append to `log.md`:** `## [YYYY-MM-DD] compile | N paper pages created/updated` with a body line listing the paper-ids.

10. **Commit inside the wiki's own repo:**
    ```bash
    git -C "$WIKI_ROOT" add .
    git -C "$WIKI_ROOT" commit -m "compile: <N> papers: <first-paper-id>, ..."
    ```
    Use `compile: paper-only <N> papers: ...` when `--paper-only` was set.

11. **Release lock** (trap handles this on exit).

### Steps (batch mode)

Batch mode replaces the per-paper loop with wave-based parallel subagents. Full orchestration logic is in `references/compilation-guide.md` "Batch compile mode". Summary:

1. **Acquire lockfile** (same as sequential path).
2. **Create or resume checkpoint** at `outputs/.compile-checkpoint.yml`.
3. **Partition pending papers into waves** (3 subagents per wave; wave-size depends on tier — see `references/compilation-guide.md`).
4. **For each wave:** spawn Haiku subagents in parallel (`run_in_background: true`, `model: "haiku"`, `mode: "auto"`). Each subagent receives a batch of `{paper-id, extract-path}` tuples. For full-tier batches, use `references/batch-compile-full-prompt.md` (interpolating `{{PRE_BATCH_PAPERS}}`, `{{PRE_BATCH_SNAPSHOT_PATH}}`, `{{TODAY}}`, plus the existing `{{WIKI_ROOT}}`, `{{PAPER_LIST}}`, `{{PYTHONPATH}}`); for paper-only, use `references/batch-compile-prompt.md`. Subagents write `wiki/papers/`, `wiki/venues/`, and — for full-tier — `wiki/concepts/`, `wiki/methods/`, `wiki/open-problems/`, and candidate entries under `outputs/reports/`.
5. **Collect results:** parse subagent output, update checkpoint, commit wave.
6. **Retry failed papers** in a single retry wave.
6b. **Final orchestrator pass** (full-tier only): resolve intra-batch cites + backlinks. See compilation-guide.md "Final orchestrator pass (full-tier only)". Transitions `final-pass-status` from `pending` to `in-progress` to `ok`.
7. **Squash wave commits** into one commit (fall back to keeping wave commits if squash fails).
8. **Update index.md + log.md**, delete checkpoint, final commit.
9. **Release lockfile.**

Batch mode honors the `--paper-only` flag the same way the sequential path does:

- Without `--paper-only`: **full-tier batch** (paper pages + entity extraction + cites + backlinks + cross-paper candidates). See `references/compilation-guide.md` "Batch compile mode" for full orchestration.
- With `--paper-only`: paper-only batch (paper + venue pages only).

The `tier:` field on the checkpoint drives template selection on resume.

### Update conflict policy (applies to every wiki page updated by compile)

Per spec §3.6. Compile reaches this flow whenever a newly-ingested paper produces content that overlaps an existing wiki page — whether a paper page (re-compile scenario), a concept, method, open-problem, or cross-paper claim/result page.

1. **Read the existing content fully.** Use `academic_wiki_lib.frontmatter.read_frontmatter` to get frontmatter + body.
2. **Preserve prior claims.** Do NOT delete existing assertions solely because the new source doesn't mention them.
3. **Append new evidence.** Add the new paper-id to `sources:` (or to `cites:` for paper pages). Incorporate new content in a clearly attributed paragraph or section (e.g., "In <paper-title> (<year>), the authors report...").
4. **Flag contradictions inline.** When the new source's content is in tension with existing content, insert an Obsidian callout at the point of disagreement:
    ```markdown
    > [!WARNING] Contradiction with [[other-paper-id]]
    > <Paper A> claims X, but <Paper B> (cited above) claims Y. Needs resolution.
    ```
    Never silently overwrite either side.
5. **Never replace without provenance.** Every material claim on a wiki page must trace to ≥1 `paper-id` in `sources:`. If an LLM cannot attribute a claim to a source, the claim is dropped OR marked `status: stale`.
6. **Bump `updated:` frontmatter** to today's date.
7. **Do not change `created:`** — it reflects first creation, never re-bumps.
8. **Aliases:** if a rename/merge happens during update (unusual), add the former slug to the target page's `aliases: []` list. Lint resolves `[[old-slug]]` via alias lookup.
9. **Log the merge** — the compile commit message should summarize: `compile: merged <new-paper-id> into <N> existing pages` (replaces the default `compile: <N> papers: ...` subject when merging into existing pages).

## `query <question>`

Answer a question against the wiki's paper pages and entity pages (concepts, methods, etc.). Files the answer for future reuse.

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

4. **Read all candidate paper pages.** Follow one level of wikilinks if the linked target is any existing wiki page (paper, concept, method, open-problem, result, claim).

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

## `lint [--fix-dead-links] [--suggest-backlinks] [--with-suggestions]`

Audit wiki integrity via a deterministic Python script plus opt-in LLM-assisted passes.

### Setup variables

    PY=~/.venv/bin/python
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    WIKI_ROOT="<active-wiki-path>"
    SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/lint-wiki.py"

Lint is read-only by default. Only the opt-in `--fix-*` passes acquire the lockfile.

### Steps

1. **Run deterministic checks:**
    ```bash
    "$PY" "$SCRIPT" "$WIKI_ROOT" \
        > "$WIKI_ROOT/outputs/reports/$(date +%Y-%m-%d)-lint.md" \
        2>&1
    REPORT="$WIKI_ROOT/outputs/reports/$(date +%Y-%m-%d)-lint.md"
    ```

    The script emits tagged lines like:
    - `DEAD_LINK: [[foo]] in wiki/concepts/bar.md:12`
    - `ALIAS_LINK: [[old]] in wiki/... resolves to [[new]] — consider rewriting`
    - `ORPHAN: wiki/concepts/foo.md has no inbound links`
    - `MISSING_FIELD: wiki/... lacks required field 'sources' for type 'concept'`
    - `MISSING_FIELD_TAG: wiki/...`
    - `MISSING_SECTION: ... lacks 'Counter-Arguments and Gaps'`
    - `STALE: ...`
    - `INVALID_CITES: ... cites unknown paper-id [...]`
    - `MISSING_BIBTEX: ...`
    - `INDEX_DRIFT: ...`
    - `VERSION_DRIFT: ...`
    - `EXTRACT_MISSING: ...`, `EXTRACT_FAILED: ...`
    - `CONTRADICTION: ... has [!WARNING] callout`
    - `PARSE_ERROR: ...` / `EXTRACT_PARSE_ERROR: ...`

2. **Opt-in pass `--fix-dead-links`:** LLM creates stubs for each `DEAD_LINK` issue. Before running, acquire the lockfile:
    ```bash
    "$PY" -c "import sys; sys.path.insert(0, '$PYTHONPATH'); from academic_wiki_lib.lockfile import acquire; acquire('$WIKI_ROOT/.lock', op='lint')"
    trap '"$PY" -c "import sys; sys.path.insert(0, \"'$PYTHONPATH'\"); from academic_wiki_lib.lockfile import release; release(\"'$WIKI_ROOT'/.lock\")"' EXIT
    ```

    For each `DEAD_LINK: [[foo]] in <file>:<line>`:
    - Read `<file>` at `<line>` to get the surrounding context.
    - Use LLM judgment to infer the target's entity type from the usage:
      - If the context is prose like "using the [[foo]] method", type = `method`.
      - If "the concept of [[foo]]", type = `concept`.
      - If "the open problem of [[foo]]", type = `open-problem`.
      - If none of the above fits, default to `concept`.
    - Create a minimal stub at `wiki/<entity-type>s/foo.md` with frontmatter per §3 template and body placeholder text.
    - Populate `sources:` with whatever paper-ids appear in the same line or nearby paragraph.
    - Tag with `field/*` inherited from the referring page's tags.
    - Commit: `lint: created <N> dead-link stubs`.

3. **Opt-in pass `--suggest-backlinks`:** LLM identifies pages that SHOULD link to existing entity pages but currently don't (based on textual mentions that didn't get wikilinked during compile).
    - For each entity page slug (≥2-word slugs only), search the wiki body for the slug's words appearing in prose.
    - Propose edits as a diff (do NOT apply silently) written to `outputs/reports/YYYY-MM-DD-backlink-suggestions.md`.
    - User can review and apply manually (or via a future command).
    - Commit the suggestions report: `lint: suggested N backlinks (review required)`.

4. **Opt-in pass `--with-suggestions`:** LLM reads the full lint report + a sampling of wiki content and adds a "Suggested Next Steps" section:
    - 3-5 questions the wiki can't yet answer well (from gaps in content).
    - 2-3 specific source suggestions that would strengthen gap areas.
    - Append to the lint report file.

5. **Append to `log.md`:** `## [YYYY-MM-DD] lint | <N> issues found` (if deterministic only), or `## [YYYY-MM-DD] lint | <N> issues, <M> fixed` (if `--fix-dead-links` was used).

6. **Commit the report file (deterministic checks always produce this):**
    ```bash
    git -C "$WIKI_ROOT" add outputs/reports/
    git -C "$WIKI_ROOT" commit -m "lint: <YYYY-MM-DD> (<N> issues)"
    ```

7. **Release lockfile** (if acquired for a --fix-* pass).

### Exit semantics

- Lint itself never fails the user's session. Issues are reported, not gated.
- If an opt-in fix pass fails partway, the trap releases the lock and the user can retry with the remaining issues.
- The deterministic script exits 0 even when issues are found; the exit code reflects script execution success, not issue count.

### Reading the report

The report at `outputs/reports/YYYY-MM-DD-lint.md` is plain text with one issue per line. LLM should summarize key findings to the user:
- Total issue count by tag.
- Top-3 most concerning issues (e.g., CONTRADICTION, EXTRACT_FAILED, INVALID_CITES that have high impact).
- Recommended next action (e.g., "Run lint --fix-dead-links to auto-create 5 stub pages").

## `export-bibtex <selectors>`

Generate a consolidated `.bib` file for a subset of papers (e.g., all papers tagged with a research-project slug, ready to paste into LaTeX). See `references/bibtex-handling.md` for detail.

### Setup variables

    PY=~/.venv/bin/python
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    WIKI_ROOT="<active-wiki-path>"
    SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/bibtex-export.py"

Export acquires the lockfile during the output write step; commits the result.

### Selectors

At least one of `--project`, `--field`, `--tag`, `--query`, `--keys`, `--since` must be provided. Multiple selectors combine with AND semantics. `--label <string>` is optional; used verbatim (only filesystem-unsafe chars stripped).

### Steps

1. **Resolve `--query` (if provided) via search backend:** the `--query` flag isn't handled by the CLI directly — SKILL layer resolves it first. Invoke `query`-style Phase 1/Phase 2 search against paper pages, collect the matching paper-ids, and pass them as `--keys` to the CLI instead. This makes `--query` transparently work through the same pipeline.

    ```bash
    # Pseudo-code:
    if [[ -n "$QUERY_TEXT" ]]; then
        matched_pids=$(run_search_against_paper_pages "$QUERY_TEXT")
        export_args="--keys ${matched_pids//$'\n'/,} $OTHER_ARGS"
    else
        export_args="$ORIGINAL_ARGS"
    fi
    ```

2. **Acquire lockfile:**
    ```bash
    "$PY" -c "import sys; sys.path.insert(0, '$PYTHONPATH'); from academic_wiki_lib.lockfile import acquire; acquire('$WIKI_ROOT/.lock', op='export')"
    trap '"$PY" -c "import sys; sys.path.insert(0, \"'$PYTHONPATH'\"); from academic_wiki_lib.lockfile import release; release(\"'$WIKI_ROOT'/.lock\")"' EXIT
    ```

3. **Invoke the CLI:**
    ```bash
    "$PY" "$SCRIPT" "$WIKI_ROOT" $export_args
    ```

    CLI writes `outputs/bib/YYYY-MM-DD-<label>.bib` and prints a summary:
    - `Exported N papers to <path>`
    - `M papers have bib-incomplete issues:` (if any)
    - On failure: `No papers match the selector(s).` or `No usable BibTeX entries found for N selected papers.`

4. **Append to `log.md`:**
    ```
    ## [YYYY-MM-DD] export | <label> (<N> papers)
    ```

5. **Commit inside the wiki's own repo:**
    ```bash
    git -C "$WIKI_ROOT" add outputs/bib/ log.md
    git -C "$WIKI_ROOT" commit -m "export: <label> (<N> papers)"
    ```

6. **Release lockfile** (trap handles it).

### Reading the output

`outputs/bib/YYYY-MM-DD-<label>.bib` is a plain BibTeX file. Paste into LaTeX or pass to a bib manager. Each entry has a `% <paper-id>` comment line immediately before the `@type{key,...}` — so you can map back to the wiki page if needed.

### Common usage patterns

- **For a paper draft:** `/academic-wiki:wiki export-bibtex --project rsma-survey-2025`
  Tag every relevant wiki page with `#project/rsma-survey-2025` as you write, then export at submission time.

- **For a field-scoped review:** `/academic-wiki:wiki export-bibtex --field nlp --since 2024-01-01`
  Only papers tagged `field/nlp` ingested since 2024-01-01.

- **For an ad-hoc set:** `/academic-wiki:wiki export-bibtex --keys vaswani2017attention,bahdanau2014neural --label icml-rebuttal`
  Explicit paper-id list + custom label.

### `--query` vs `--keys`

- `--query`: LLM/search finds papers; you describe the topic in prose.
- `--keys`: you explicitly list paper-ids.

Use `--keys` when you know exactly what to export; use `--query` when you want the wiki to help find relevant papers.

## `snapshot <label>`

Tag the wiki's state for reproducibility — e.g., the state when you submitted a paper. Operates on the wiki's own nested git repo so the tag captures ONLY wiki state, not unrelated Obsidian vault changes.

### Setup variables

    PY=~/.venv/bin/python
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    WIKI_ROOT="<active-wiki-path>"
    LABEL="<user-supplied-label>"

### Steps

1. **Acquire lockfile:**
    ```bash
    "$PY" -c "import sys; sys.path.insert(0, '$PYTHONPATH'); from academic_wiki_lib.lockfile import acquire; acquire('$WIKI_ROOT/.lock', op='snapshot')"
    trap '"$PY" -c "import sys; sys.path.insert(0, \"'$PYTHONPATH'\"); from academic_wiki_lib.lockfile import release; release(\"'$WIKI_ROOT'/.lock\")"' EXIT
    ```

2. **Validate label.** Require a non-empty label. Git tag names cannot contain spaces, `~`, `^`, `:`, `?`, `*`, `[`, `\`, or end in `.lock`. Sanitize by replacing whitespace with `-` and rejecting invalid characters:
    ```bash
    if [[ -z "$LABEL" ]]; then
        echo "Error: snapshot requires a <label> argument." >&2
        exit 2
    fi
    # Sanitize: replace whitespace with hyphens
    LABEL_SANITIZED=$(echo "$LABEL" | tr '[:space:]' '-')
    # Reject labels with invalid git-tag characters
    if [[ "$LABEL_SANITIZED" =~ [[:space:]~^:?*\[\\] ]] || [[ "$LABEL_SANITIZED" =~ \.lock$ ]]; then
        echo "Error: label '$LABEL_SANITIZED' contains characters invalid in git tag names." >&2
        exit 2
    fi
    ```

3. **Check for a tag collision.** If `snapshot/$LABEL_SANITIZED` already exists, abort:
    ```bash
    if git -C "$WIKI_ROOT" rev-parse --verify "snapshot/$LABEL_SANITIZED" >/dev/null 2>&1; then
        echo "Error: tag snapshot/$LABEL_SANITIZED already exists." >&2
        echo "Use a different label or delete the existing tag with: git -C $WIKI_ROOT tag -d snapshot/$LABEL_SANITIZED" >&2
        exit 3
    fi
    ```

4. **Verify working tree is clean.** Uncommitted changes would not be captured by the tag, so require a clean state:
    ```bash
    status=$(git -C "$WIKI_ROOT" status --porcelain)
    if [[ -n "$status" ]]; then
        echo "Error: uncommitted changes in the wiki — commit or stash before snapshot." >&2
        echo "$status" >&2
        exit 4
    fi
    ```

5. **Append to `log.md` BEFORE tagging** (so the log entry is included in the snapshot):
    ```bash
    SHA=$(git -C "$WIKI_ROOT" rev-parse HEAD)
    # Current HEAD sha before the log update
    DATE=$(date +%Y-%m-%d)
    cat >> "$WIKI_ROOT/log.md" <<EOF

    ## [$DATE] snapshot | $LABEL_SANITIZED
    Tagged at $SHA
    EOF
    ```

6. **Commit the log update:**
    ```bash
    git -C "$WIKI_ROOT" add log.md
    git -C "$WIKI_ROOT" commit -m "snapshot: $LABEL_SANITIZED"
    NEW_SHA=$(git -C "$WIKI_ROOT" rev-parse HEAD)
    ```

7. **Create the git tag** (annotated, so the tag carries a message):
    ```bash
    git -C "$WIKI_ROOT" tag -a "snapshot/$LABEL_SANITIZED" -m "snapshot: $LABEL_SANITIZED" "$NEW_SHA"
    ```

8. **Release lockfile** (trap handles it).

9. **Print confirmation:**
    ```
    Tagged snapshot/$LABEL_SANITIZED at $NEW_SHA.
    Revisit with: git -C "$WIKI_ROOT" checkout snapshot/$LABEL_SANITIZED
    List all snapshots: git -C "$WIKI_ROOT" tag --list 'snapshot/*'
    ```

### Design notes

- **Tag namespace `snapshot/*`**: keeps the tag space organized. If you later want other tag conventions (e.g., `paper/*` for paper-submission tags), they won't collide.
- **Annotated tags**: `-a` creates an annotated tag with author/date/message metadata, which is richer than a lightweight tag and survives `git push --follow-tags`.
- **Log-then-tag order**: the `log.md` update is committed BEFORE tagging, so the snapshot includes its own log entry. Reading the wiki from the snapshot shows the snapshot itself as an event.

### Recovery — revisiting a snapshot

```bash
# List all snapshots
git -C "$WIKI_ROOT" tag --list 'snapshot/*'

# Check out a snapshot (detached HEAD)
git -C "$WIKI_ROOT" checkout snapshot/icc-2026-submission

# Return to the current state
git -C "$WIKI_ROOT" checkout -  # or `git checkout main/master/whatever-branch`
```

### Deleting a snapshot

Rarely needed, but:
```bash
git -C "$WIKI_ROOT" tag -d snapshot/<label>
```
This removes only the tag, not the underlying commits. A tag deletion is NOT logged in `log.md` by the snapshot command — manually append a note if you care.

## `remove <name>`

Delete a wiki and its nested git repo after explicit confirmation. Destructive — all wiki content, commits, and tags are lost.

### Setup variables

    PY=~/.venv/bin/python
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
    NAME="<name>"
    WIKI_ROOT="$HOME/Documents/Obsidian Vault/03-Resources/$NAME"
    QMD="${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd"

### Steps

1. **Validate argument.** Require a non-empty `<name>`. Reject names with path separators (`/` or `\`) to prevent arbitrary path deletion:
    ```bash
    if [[ -z "$NAME" ]]; then
        echo "Error: remove requires a <name> argument." >&2
        exit 2
    fi
    if [[ "$NAME" =~ [/\\] ]]; then
        echo "Error: name must not contain path separators." >&2
        exit 2
    fi
    ```

2. **Check the wiki exists:**
    ```bash
    if [[ ! -d "$WIKI_ROOT" ]]; then
        echo "Error: wiki '$NAME' does not exist at $WIKI_ROOT." >&2
        exit 3
    fi
    ```

3. **Show what will be deleted:**
    ```bash
    echo "About to delete wiki '$NAME' at $WIKI_ROOT."
    echo "Contents:"
    ls "$WIKI_ROOT/" 2>/dev/null | head -20
    COMMIT_COUNT=$(git -C "$WIKI_ROOT" rev-list --count HEAD 2>/dev/null || echo "0")
    TAG_COUNT=$(git -C "$WIKI_ROOT" tag | wc -l | tr -d ' ')
    echo "History: $COMMIT_COUNT commits, $TAG_COUNT tags (ALL will be lost)."
    ```

4. **Explicit confirmation prompt.** The LLM must ask the user to type the wiki name as confirmation:
    ```
    This will PERMANENTLY delete wiki '$NAME' and its git history at $WIKI_ROOT.
    Type the wiki name exactly to confirm (or anything else to cancel):
    ```
    If the user types anything other than the exact `$NAME`, abort:
    ```bash
    if [[ "$user_response" != "$NAME" ]]; then
        echo "Cancelled — name did not match."
        exit 0
    fi
    ```

5. **Acquire the lockfile to prevent concurrent mutation during removal:**
    ```bash
    "$PY" -c "import sys; sys.path.insert(0, '$PYTHONPATH'); from academic_wiki_lib.lockfile import acquire; acquire('$WIKI_ROOT/.lock', op='remove')"
    # NO trap for release — the lock file goes away with the directory.
    ```

6. **Remove the qmd collection if installed:**
    ```bash
    if [[ -x "$QMD" ]]; then
        env -u BUN_INSTALL "$QMD" collection remove "$NAME" 2>/dev/null || true
    fi
    ```

7. **Remove the directory and its nested git repo entirely:**
    ```bash
    rm -rf "$WIKI_ROOT"
    ```

8. **Update the Obsidian vault's `.gitignore` if present** — remove the entry for this wiki:
    ```bash
    VAULT="$HOME/Documents/Obsidian Vault"
    GITIGNORE="$VAULT/.gitignore"
    if [[ -f "$GITIGNORE" ]]; then
        # Remove any line matching `03-Resources/$NAME/` exactly
        python3 -c "
    import sys
    path = '$GITIGNORE'
    entry = '03-Resources/$NAME/'
    with open(path) as f:
        lines = f.readlines()
    lines = [l for l in lines if l.rstrip() != entry]
    with open(path, 'w') as f:
        f.writelines(lines)
    "
    fi
    ```

9. **If the vault is itself a git repo, commit the removal:**
    ```bash
    VAULT="$HOME/Documents/Obsidian Vault"
    if [[ -d "$VAULT/.git" ]]; then
        (
            cd "$VAULT"
            git add -u || true  # Track the removal
            git commit -m "remove: $NAME wiki" 2>/dev/null || true
        )
    fi
    ```

10. **Print confirmation:**
    ```
    Wiki '$NAME' removed.
    ```

### Design notes

- **Double confirmation** (type-the-name prompt) is deliberate. The plugin never auto-confirms destructive ops.
- **`-rf`** is the right flag — the directory includes its own `.git/` subdirectory and we want both gone.
- **Lock acquisition before rm** — prevents a concurrent `ingest`/`compile`/etc. from racing the deletion and writing to a half-gone directory.
- **Vault .gitignore cleanup** — the `init` command added the entry; `remove` removes it for symmetry.
- **No trap for lock release** — the lock file goes away with the directory itself.

### Post-removal recovery

If the deletion was accidental AND the vault is a git repo:
```bash
cd ~/Documents/"Obsidian Vault"
git reflog                          # find the pre-removal commit
git checkout <pre-remove-sha> -- "03-Resources/$NAME/"
```

If the wiki was NOT under the vault's git (typical — the nested repo was self-contained), recovery requires external backups. The plugin has no built-in undo.

## Marp slide export

Any wiki page can be exported as a slide deck using Marp (Markdown-based presentations).

### Setup

Marp CLI is installed automatically by the SessionStart hook to:

    ${CLAUDE_PLUGIN_DATA}/node_modules/.bin/marp

If it's missing, install manually:

    cd "${CLAUDE_PLUGIN_DATA}" && npm install @marp-team/marp-cli

### Adding Marp frontmatter

Edit any wiki page (e.g., a concept page) and add these fields to the existing frontmatter:

    ---
    ...existing frontmatter...
    marp: true
    theme: default
    paginate: true
    ---

Then structure the body with `---` separators between slides:

    # Slide 1 title

    Content goes here.

    ---

    # Slide 2 title

    - bullet
    - another bullet

    ---

    # Slide 3

    Summary.

### Rendering

Export to HTML (browser-renderable):

    MARP="${CLAUDE_PLUGIN_DATA}/node_modules/.bin/marp"
    "$MARP" "${WIKI_ROOT}/wiki/concepts/my-concept.md" -o output.html

Export to PDF (requires Chromium; first run downloads it):

    "$MARP" --pdf "${WIKI_ROOT}/wiki/concepts/my-concept.md" -o output.pdf

Export to PPTX:

    "$MARP" --pptx "${WIKI_ROOT}/wiki/concepts/my-concept.md" -o output.pptx

### Query auto-rendering (slides mode)

When a `/academic-wiki:wiki query` question contains "slides", the synthesized answer gets `marp: true` frontmatter AND is rendered to HTML in the same directory as the query-output file:

    /academic-wiki:wiki query "Give me slides on the key insights of attention mechanisms"

produces:

    wiki/queries/give-me-slides-on-the-key-insights-of-attention-mechanisms.md   ← source
    wiki/queries/give-me-slides-on-the-key-insights-of-attention-mechanisms.html ← rendered

Users can then `open <path>.html` to view the deck in a browser.

### Obsidian integration

The Obsidian Marp plugin (separate install — search in Community Plugins for "Marp") gives you:
- A preview pane for `marp: true` pages.
- Built-in export buttons (HTML / PDF / PPTX) via the command palette.

Both ways of rendering (Obsidian plugin OR `marp-cli` CLI) produce equivalent output. Use whichever fits your workflow.

### Tips

- **Themes**: `theme: default` is the built-in theme. You can also use `theme: gaia` or `theme: uncover`. Custom themes require a CSS file — see Marp docs.
- **Math**: Marp supports LaTeX via KaTeX. Write equations as `$...$` (inline) or `$$...$$` (display). The wiki uses the same convention, so math in wiki pages carries over directly.
- **Figures**: `![image description](raw/figures/<paper-id>/fig-1.png)` works if you use paths relative to the wiki root. Obsidian's embed syntax `![[fig-1.png]]` does NOT render in Marp — use standard markdown image syntax.
- **Paginate**: `paginate: true` shows slide numbers. Skip for title/cover slides via `_paginate: false` in a per-slide directive.
