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

<Wave 1 Task 1.13 fills this in.>

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
