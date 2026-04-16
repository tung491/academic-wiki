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
<TO BE FILLED — spec §2.2>

## Identity Model
<TO BE FILLED — spec §2.3 #2 + §3.1>

## Entity Types
<TO BE FILLED — spec §3.1–§3.3>

## Cross-Schema Conventions
<TO BE FILLED — spec §3.4>

## Slug Generation
<TO BE FILLED — spec §3.5>

## Update Conflict Policy
<TO BE FILLED — spec §3.6>

## Raw-Side Metadata Schema
<TO BE FILLED — spec §3.7>

## Tag Taxonomy
<TO BE FILLED — spec §4>

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
<TO BE FILLED — wikilink density, backlink audit allowlist, contradiction callouts>

## Ingest Rules
<TO BE FILLED — spec §5.2>

## Compile Rules
<TO BE FILLED — spec §5.3 (paper-only tier in Wave 1; full tier in Wave 2)>

## Query Rules
<TO BE FILLED — spec §5.4>

## Lint Rules
<TO BE FILLED — spec §5.5>

## Export-BibTeX Rules
<TO BE FILLED — spec §5.6>

## Snapshot Rules
<TO BE FILLED — spec §5.7 — wiki's own git repo, tag namespace>

## Search Strategy
<TO BE FILLED — spec §6 — SearchHit contract and fallback chain>

## Lockfile Semantics
<TO BE FILLED — spec §8.1>
"""
