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
    Compare extracted identifiers against every existing paper page's `identifiers:`. If any non-empty identifier matches (`doi`, `arxiv` ignoring version, `url`), the paper already exists — load its `paper-id` and go to step 8 (version handling). Otherwise proceed.

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

9. **Metadata-extraction failure fallback:** if metadata cannot be extracted cleanly (scanned PDF without OCR, garbage identifier, etc.), use fallback `paper-id` = `unknown-<current-year>-<filename-slug>` for ALL file basenames consistently. Set `metadata-incomplete: true` in the extract frontmatter. Lint will surface this.

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

<Wave 1 Task 1.14 fills this in with the paper-only tier; Wave 2 extends.>

## `query <question>`

<Wave 1 Task 1.15 fills this in.>

## `lint [--fix-dead-links] [--suggest-backlinks] [--with-suggestions]`

<Wave 3 fills this in.>

## `export-bibtex <selectors>`

<Wave 3 fills this in.>

## `snapshot <label>`

<Wave 3 fills this in.>

## `remove <name>`

<Wave 4 fills this in.>
