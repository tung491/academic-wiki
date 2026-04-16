# Ingestion Routing

Input-type autodetection for `/academic-wiki:wiki ingest <input>`:

| Pattern (regex / prefix) | Handler |
|---|---|
| `^\d{4}\.\d{4,5}(v\d+)?$` | arXiv ID → `mcp__agentic-rag-v2__download_arxiv` |
| `^10\.\d+/.+` | DOI → `mcp__agentic-rag-v2__doi2content` |
| URL: `arxiv.org/abs/<id>` or `arxiv.org/pdf/<id>` | Extract arXiv ID (preserve version if present, e.g. `1706.03762v5`) → arXiv handler |
| URL with publisher hostname (IEEE, ACM, Elsevier / ScienceDirect, Springer, Nature, Science, MDPI) | `mcp__agentic-rag-v2__fetch_publisher_html` |
| Local path ending `.pdf` | `ocr-papers-to-latex` skill — returns LaTeX-rich markdown |
| Local path ending `.md`, `.markdown`, `.tex` | Treat as pre-extracted. Copy into `raw/papers/<paper-id>.md` (or `.tex`) AND into `raw/extracts/<paper-id>.md` directly. |
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

For local `.md`/`.tex`: the file itself serves as the extract; a copy goes to `raw/papers/` and an identical copy to `raw/extracts/`.

## Post-routing pipeline (spec §5.2 steps 2–16)

After the handler returns, the pipeline continues in this order:

1. Compute `source-sha` (SHA-256 of the raw source file).
2. Dedup pass 1 — byte-level: scan `raw/extracts/*.md` frontmatter for matching `source-sha`. If found, release lock, print existing `paper-id`, exit.
3. Extract metadata: first-author last name (ASCII-folded, lowercased), 4-digit year, title's first meaningful word (skip stop words `a`/`an`/`the` and pure numerals), identifiers dict.
4. Dedup pass 2 — identifier-level: compare `doi`, `arxiv` (ignoring version), `url` against all existing paper pages' `identifiers:`. If matched, reuse existing `paper-id` and go to version handling (step 8). Otherwise proceed.
5. Generate `paper-id` for new papers: `<lastname>-<year>-<firstword>`. Resolve collisions with `-2`, `-3`, ... suffix.
6. Handle version updates: if identifier-level dedup matched but `source-version` differs, save new source with same `paper-id` basename, update `raw/extracts/<paper-id>.versions.yml`, update `wiki/papers/<paper-id>.md` identifiers.
7. Metadata-extraction failure fallback: if metadata is unextractable, use `paper-id` = `unknown-<current-year>-<filename-slug>`; set `metadata-incomplete: true`.
8. Save files: `raw/papers/<paper-id>.<ext>`, `raw/extracts/<paper-id>.md`, `raw/bib/<paper-id>.bib`, `raw/figures/<paper-id>/`.
9. Write extract frontmatter per spec §3.7.
10. Save or stub BibTeX (`% bib-incomplete: true` comment at top if stubbed).
11. Append to `log.md`, commit inside the wiki's own git repo, release lock.
