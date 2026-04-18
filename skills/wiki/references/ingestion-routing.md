# Ingestion Routing

Input-type autodetection for `/academic-wiki:wiki ingest <input>`:

| Pattern (regex / prefix) | Handler |
|---|---|
| `^\d{4}\.\d{4,5}(v\d+)?$` | arXiv ID → `mcp__agentic-rag-v2__download_arxiv` |
| `^10\.\d+/.+` | DOI → `mcp__agentic-rag-v2__doi2content` |
| URL: `arxiv.org/abs/<id>` or `arxiv.org/pdf/<id>` | Extract arXiv ID (preserve version if present, e.g. `1706.03762v5`) → arXiv handler |
| URL with publisher hostname (IEEE, ACM, Elsevier / ScienceDirect, Springer, Nature, Science, MDPI) | `mcp__agentic-rag-v2__fetch_publisher_html` |
| Local path ending `.pdf` | `ocr-papers-to-latex` skill — returns LaTeX-rich markdown |
| Local directory containing ≥1 `.md` + optional `images/` | Clipper handler: find `.md` inside, read frontmatter + body, edit `.md` in place (merge missing fields), symlink `images/` to `raw/figures/<paperid>`. No `raw/extracts/` copy — clipper `.md` IS the extract. |
| Local path ending `.md`, `.markdown`, `.tex` | Treat as pre-extracted. Read content + infer metadata from frontmatter/body. Handler returns (content, metadata). The main pipeline saves copies to `raw/papers/<paper-id>.*` and `raw/extracts/<paper-id>.md` in step 10, after paper-id is assigned. |
| Everything else (bare string, unrecognized URL) | Ask user to disambiguate |

Match patterns in order; first match wins. For arXiv URLs, extract the arXiv ID from the path including any version suffix (`v5`, `v12`, etc.) before passing to the arXiv handler.

## Publisher hostname list (for URL routing)

These hostnames trigger `fetch_publisher_html`:

- `ieeexplore.ieee.org`
- `dl.acm.org`
- `www.sciencedirect.com`, `linkinghub.elsevier.com`
- `link.springer.com`, `springer.com`
- `www.nature.com`
- `www.science.org`
- `www.mdpi.com`

All other hostnames fall through to the "ask user" branch.

## After routing: what the handler returns

Every handler produces two outputs passed into the pipeline:

1. **Raw bytes/text** — saved as `raw/papers/<paper-id>.<ext>`.
2. **Metadata dict** — whatever the handler can supply: title, authors, year, abstract, identifiers (`doi`, `arxiv`, `arxiv-version`, `url`), BibTeX.

For local `.pdf`: the `ocr-papers-to-latex` skill returns LaTeX-rich markdown as the extract; the original PDF is the source file.

For local `.md`/`.tex`: the file itself serves as the extract; the handler returns the content and metadata — the pipeline places copies at `raw/papers/` and `raw/extracts/` after the `paper-id` is assigned in steps 5–7.

## Post-routing pipeline (spec §5.2 steps 2–16)

After the handler returns, the pipeline continues in this order:

1. Compute `source-sha` (SHA-256 of the raw source file).
2. Dedup pass 1 — byte-level: scan BOTH `raw/extracts/*.md` AND `raw/papers/*/` clipper `.md` files for matching `source-sha` in frontmatter. If found, release lock, print existing `paper-id`, exit.
3. Extract metadata: first-author last name (ASCII-folded, lowercased), 4-digit year, title's first meaningful word (skip stop words `a`/`an`/`the` and pure numerals), identifiers dict.
4. Dedup pass 2 — identifier-level: compare `doi`, `arxiv` (ignoring version), `url` against all existing paper pages' `identifiers:`. If matched, reuse existing `paper-id` and go to version handling (step 8). Otherwise proceed.
5. Generate `paper-id` for new papers: `<lastname><year><firstword>` (no separators). Resolve collisions with `2`, `3`, ... suffix appended directly (no separator). `resolve_collision()` checks both `wiki/papers/*.md` filenames AND `paper-id` values in clipper `.md` frontmatter under `raw/papers/*/`.
6. Handle version updates: if identifier-level dedup matched but `source-version` differs, save new source with same `paper-id` basename, update `raw/extracts/<paper-id>.versions.yml`, update `wiki/papers/<paper-id>.md` identifiers.
7. Metadata-extraction failure fallback: if metadata is unextractable, use `paper-id` = `unknown<currentyear><filenameslug>`; set `metadata-incomplete: true`.
8. Save files: `raw/papers/<paper-id>.<ext>`, `raw/extracts/<paper-id>.md`, `raw/bib/<paper-id>.bib`, `raw/figures/<paper-id>/`.
9. Write extract frontmatter per spec §3.7.
10. Save or stub BibTeX (`% bib-incomplete: true` comment at top if stubbed).
11. Append to `log.md`, commit inside the wiki's own git repo, release lock.

## Handler contract

Each handler returns:
- `content`: the raw bytes or text of the source
- `metadata`: dict with keys `title`, `authors`, `year`, `doi`, `arxiv`, `arxiv-version`, `url`, `source-type`, etc. (any may be missing)
- `bibtex`: optional BibTeX string if the handler fetched it

The main pipeline (steps 3-11) takes the handler's returns and does: source-sha → dedup → metadata-to-paper-id → save-with-paper-id-basename. No handler writes to `raw/` directly; they return data for the pipeline to place.

## Batch scan mode

`ingest` with no path argument scans `raw/papers/*/` for unprocessed clipper directories:

1. Walk `raw/papers/*/` looking for directories containing ≥1 `.md` file.
2. Filter to unprocessed: no `paper-id` in `.md` frontmatter, OR `paper-id` present but `extract-status` absent/not `complete` (crash recovery).
3. One `acquire()` before the loop, one `release()` after (not per-directory). EXIT trap set once.
4. Process each directory sequentially. Papers processed earlier in the batch are visible to later papers' dedup scans (their `paper-id` is already written to frontmatter).
5. Print summary: `Ingested N papers from raw/papers/`.

## Clipper directory in-place ingest

For a clipper directory (detected via batch scan or explicit path):

1. Find the `.md` file inside (the clipper writes exactly one).
2. Read existing frontmatter with `read_frontmatter()` — do NOT overwrite user/clipper fields like `title`, `doi`, `date`, `venue`.
3. Run standard metadata pipeline to extract first-author → year → first-word → generate `paper-id`.
4. Run dedup passes (byte-level + identifier-level, scoped over both extracts/ and clipper dirs).
5. Merge missing fields into the frontmatter and write back with `write_frontmatter()`. Fields to inject:
    - `paper-id`
    - `source-sha`
    - `source-type: clipper-md`
    - `source-url` — `https://doi.org/<doi>` if present, else URL from clipper frontmatter if present, else `null`
    - `extracted-at` (ISO-8601 UTC)
    - `extract-status: complete`
    - `extractor: obsidian-clipper`
    - `ocr-used: false`
    - `extract-warnings: []`
6. If `images/` subdirectory exists: create a **relative** symlink `raw/figures/<paperid>` → `../papers/<clipper-dir-name>/images/` (the relative form survives vault relocation).
7. Leave image references (`![[fig1.png]]`) untouched — Obsidian resolves vault-wide.
8. Stub BibTeX to `raw/bib/<paperid>.bib` as usual.
9. Log + commit.

**Differences from standard ingest:**
- No `raw/extracts/<paperid>.md` created — clipper `.md` IS the extract.
- No `raw/papers/<paperid>.*` copy — clipper directory is the canonical source.
- Figures are symlinked, not copied.
