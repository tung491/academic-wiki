# Academic Wiki MCP Server — Design Spec

**Date:** 2026-04-17
**Status:** Draft
**Author:** Tung Son Do + Claude

## Overview

A dedicated FastMCP server for the academic wiki that downloads papers from publisher websites and discovers related work via Semantic Scholar. It extracts structured content (metadata, sections, figures) using headless browser scraping and outputs Obsidian-flavored Markdown matching the `academic_web_clipper` Chrome extension format.

## Goals

- Download papers by DOI or arXiv ID directly from publisher pages
- Discover papers via Semantic Scholar when no direct identifier is available
- Produce output identical to `academic_web_clipper`: Obsidian Markdown with YAML frontmatter + `images/` directory
- Save directly into the wiki's `raw/papers/<paper-id>/` structure
- Support all 8 publishers the web clipper supports

## Non-Goals

- PDF-based ingestion or OCR (handled by agentic-rag-v2)
- RAG retrieval, vector indexing, or BibTeX management (handled by agentic-rag-v2 and the wiki plugin)
- Replacing the web clipper — this is a complementary server-side tool

## Project Structure

```
academic_wiki_mcp/
├── __init__.py              # FastMCP("AcademicWikiServer") instance
├── server.py                # Entry point — imports tools, runs mcp
├── config.py                # Env vars: wiki path, Semantic Scholar API key, browser prefs
├── browser.py               # Browser abstraction: Playwright first, stealth Selenium fallback
├── markdown.py              # Obsidian markdown generator (port of web clipper's lib/markdown.js)
├── identifier.py            # Detect input type: DOI, arXiv ID, or search query
├── tools/
│   ├── download.py          # download_paper(identifier, wiki_path)
│   └── discovery.py         # semantic_scholar_search(), discover_related()
└── publishers/
    ├── base.py              # Abstract publisher base class
    ├── arxiv.py
    ├── ieee.py
    ├── springer.py
    ├── sciencedirect.py
    ├── mdpi.py
    ├── wiley.py
    ├── tandfonline.py
    └── asce.py
```

Output per paper:

```
raw/papers/<paper-id>/
├── <paper-id>.md
├── fig1.png
├── fig2.png
└── ...
```

Images are stored flat alongside the markdown file (not in a subdirectory). This matches the web clipper's wikilink format: `![[fig1.png]]` resolves to a file in the same directory. Obsidian resolves wikilinks by filename, so co-locating images with the note is the simplest and most compatible layout.

## Browser Abstraction

`browser.py` defines an abstract `BrowserBackend` base class with a wrapped `Element` type. Each backend implements its own concrete `Element` wrapper, so publisher extractors never handle raw Playwright handles or Selenium WebElements directly. Elements are only valid within the backend that created them.

```python
class Element(ABC):
    """Abstract wrapper — concrete implementations hold the native handle."""
    @abstractmethod
    async def text(self) -> str: ...
    @abstractmethod
    async def attribute(self, name: str) -> str | None: ...
    @abstractmethod
    async def scroll_into_view(self) -> None: ...
    @abstractmethod
    async def click(self) -> None: ...
    @abstractmethod
    async def children(self) -> list[Element]: ...
    @abstractmethod
    async def next_sibling(self) -> Element | None: ...
    @abstractmethod
    async def parent(self) -> Element | None: ...
    @abstractmethod
    async def tag_name(self) -> str: ...

class BrowserBackend(ABC):
    async def navigate(self, url: str) -> None
    async def wait_for_selector(self, selector: str, timeout: int = 15000) -> None
    async def query_selector(self, selector: str) -> Element | None
    async def query_selector_all(self, selector: str) -> list[Element]
    async def evaluate(self, js: str, *args) -> Any: ...
    async def download_image(self, url: str) -> bytes
    async def sleep(self, ms: int) -> None: ...
    async def close(self) -> None
```

`PlaywrightBackend` and `SeleniumBackend` each provide their own `Element` subclass wrapping the native handle. Default `wait_for_selector` timeout is 15 seconds; publisher modules may pass higher values for slow-loading publishers (e.g., ScienceDirect React hydration).

The `Element` interface includes `click()`, `children()`, `next_sibling()`, `parent()`, and `tag_name()` for DOM traversal — required by publishers like T&F (click-driven popup table extraction, modal closing), ScienceDirect and MDPI (DOM-order walking rather than simple selector pulls), and Springer (sibling-based section parsing). `BrowserBackend.evaluate(js)` allows running arbitrary JS in the page context for complex extraction logic. `BrowserBackend.sleep(ms)` provides timing control for lazy-loading and animation waits.

### Fallback Strategy

Fallback is **per-publisher**, not global. Each publisher module declares its preferred backend:

```python
class IEEEPublisher(BasePublisher):
    backend = "playwright"
    fallback_backend = "selenium"
```

On a `download_paper` call:

1. Try Playwright first
2. If the page returns bot-detection (CAPTCHA, 403, Cloudflare challenge), retry with stealth Selenium (`undetected-chromedriver` + `selenium-stealth`)
3. If both fail, return an error with the failure reason

The server tracks which backend works per publisher in a module-level dict in `browser.py`. This dict persists across MCP tool calls within one server session and resets when the server restarts. If IEEE blocks Playwright once, subsequent IEEE requests go straight to Selenium for the rest of that session.

### Bot Detection Signals

A page is considered "blocked" when any of:
- HTTP status 403/429
- Page contains known CAPTCHA markers (Cloudflare challenge div, reCAPTCHA iframe)
- Page body is abnormally short (< 1KB) after load

## Publisher Extraction

Each publisher module implements three methods matching the web clipper's content script pattern:

```python
class BasePublisher(ABC):
    @abstractmethod
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata

    @abstractmethod
    async def extract_sections(self, browser: BrowserBackend) -> list[Section]

    @abstractmethod
    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]
```

### Data Model

Matches the web clipper exactly:

```python
@dataclass
class Metadata:
    title: str
    authors: list[str]
    abstract: str
    doi: str
    arxiv: str | None      # arXiv ID if applicable (e.g., "1706.03762")
    url: str               # canonical publisher URL
    date: str              # ISO format "2021-04-08" — publisher extractors normalize raw date strings
    year: int | None       # extracted integer year for paper-id generation; None if unparseable
    venue: str
    keywords: list[str]

@dataclass
class ContentBlock:
    type: str              # "paragraph" or "figure"
    text: str | None       # for paragraphs (tables are pipe-delimited text in "paragraph" blocks, matching web clipper behavior)
    figure_id: str | None  # for figure refs

@dataclass
class Section:
    heading: str
    content: list[ContentBlock]

@dataclass
class Figure:
    id: str
    url: str
    filename: str          # "fig1.png"
    caption: str
    data: bytes | None     # downloaded image bytes (None before download attempted)
    failed: bool = False   # True when download was attempted and failed
```

### Publisher Routing

URL pattern matching registry. Uses **domain suffix matching** (not exact hostname) to handle `www.` prefixes and subdomains that DOI redirects commonly land on (e.g., `www.sciencedirect.com`, `www.mdpi.com`):

```python
PUBLISHERS = [
    ("arxiv.org",              ArxivPublisher),
    ("ieeexplore.ieee.org",    IEEEPublisher),
    ("link.springer.com",      SpringerPublisher),
    ("sciencedirect.com",      ScienceDirectPublisher),
    ("mdpi.com",               MDPIPublisher),
    ("onlinelibrary.wiley.com", WileyPublisher),
    ("tandfonline.com",        TandFPublisher),
    ("ascelibrary.org",        ASCEPublisher),
]

def find_publisher(url: str) -> BasePublisher | None:
    hostname = urlparse(url).hostname or ""
    for suffix, cls in PUBLISHERS:
        if hostname == suffix or hostname.endswith("." + suffix):
            return cls()
    return None
```

For DOI inputs, the server follows the `https://doi.org/{doi}` redirect to discover the publisher domain, then picks the correct extractor. For arXiv, it navigates to `arxiv.org/html/{id}` (the full HTML rendering with `.ltx_section`, `.ltx_figure` classes). If the HTML page returns 404 (older papers without HTML rendering), falls back to `arxiv.org/abs/{id}` in **metadata-only mode**: extracts title, authors, abstract, date, and categories from the abstract page, but returns empty sections and no figures. The tool's return value includes a `partial: true` flag so the caller knows full content was not extracted.

CSS selectors for each publisher are ported from the web clipper's JS content scripts. Same fallback chain: publisher-specific selectors first, then `meta[name="citation_*"]` tags.

### Figure Handling

- Figures are extracted by collecting URLs from the page (same lazy-load scroll pattern as web clipper)
- Images are downloaded by the server (not the browser), using the browser's cookies/session for auth
- Figure deduplication via URL `Set`
- Failed downloads produce `![[fig_missing.png]]` with HTML comment

## MCP Tools

### 1. `download_paper(identifier: str, wiki_path: str) -> dict`

Smart routing via `identifier.py`:

| Input Pattern | Detection | Action |
|---|---|---|
| `10.xxxx/...` | DOI | Resolve via `doi.org` redirect → publisher extractor |
| `xxxx.xxxxx` or `arXiv:...` | arXiv ID | Navigate to `arxiv.org/html/{id}` (fallback to `/abs/{id}`) |
| Anything else | — | Error with suggestion to use `semantic_scholar_search` |

Pipeline:
1. Detect identifier type → resolve to publisher URL
2. Navigate with browser (Playwright → Selenium fallback)
3. Pick publisher extractor from `PUBLISHERS` registry
4. Extract metadata, sections, figures
5. **Dedup check** — call `find_existing_paper_by_identifiers(wiki_path, {doi, arxiv, url})` from `paper_id.py`. If a match is found, return the existing paper-id and skip download (or offer to overwrite)
6. Generate `paper-id` from metadata (see Paper-ID Generation below), then `resolve_collision()` for suffix
7. Download all figure images into `{wiki_path}/raw/papers/{paper-id}/`
8. Render Obsidian markdown → save as `{paper-id}.md`
9. Return `{ paper_id, path, title, authors, is_new }`

`wiki_path` is validated against the configured wiki root in `config.py`. Validation uses `Path.resolve()` before `Path.is_relative_to(wiki_root)` to prevent `..` traversal and symlink escapes. If the path does not exist or falls outside the wiki root, the tool returns an error.

### 2. `semantic_scholar_search(query: str, venue: str | None = None, year: str | None = None, limit: int = 10) -> list[dict]`

Searches Semantic Scholar Graph API. Returns results with: title, authors, year, venue, abstract, DOI, arXiv ID. Enough info for the user to pick a paper and call `download_paper`.

- Fields requested: `paperId, title, authors, year, venue, abstract, externalIds`
- Optional `x-api-key` from `SEMANTIC_SCHOLAR_API_KEY` env var
- Exponential backoff with retry on 429/5xx (max 5 retries)

### 3. `discover_related(identifier: str, limit: int = 10) -> dict`

Takes a DOI or arXiv ID (normalized via `identifier.py` — strips prefixes like `arXiv:`, extracts IDs from URLs), then queries three Semantic Scholar endpoints:
- **References:** `GET /graph/v1/paper/{id}/references` — papers it cites
- **Citations:** `GET /graph/v1/paper/{id}/citations` — papers that cite it
- **Recommendations:** `GET /recommendations/v1/papers/forpaper/{id}` — algorithmically recommended papers (separate base path, beta API)

The recommendations endpoint returns 404 for papers with insufficient citation context (new or obscure papers). A 404 from recommendations is treated as an empty result, not an error — the tool still returns references and citations.

Returns combined list ranked by citation count, deduplicated. Each entry includes: title, authors, year, venue, DOI, arXiv ID, citation count.

## Markdown Output Format

Ports `lib/markdown.js` from the web clipper. Output:

```markdown
---
title: "Attention Is All You Need"
authors: [Ashish Vaswani, Noam Shazeer, Niki Parmar]
inline_author: "Vaswani et al."
paper-id: "vaswani-2017-attention"
identifiers:
  doi: "10.48550/arXiv.1706.03762"
  arxiv: "1706.03762"
  url: "https://arxiv.org/html/1706.03762"
date: 2017-06-12
year: 2017
venue: "NeurIPS 2017"
keywords: [transformer, attention, sequence-to-sequence]
---

## Abstract
The dominant sequence transduction models...

## 1. Introduction
...

![[fig1.png]]
*Figure 1: The Transformer — model architecture*

## References
1. ...
```

Conventions matching the web clipper:
- `inline_author`: solo → last name, multiple → `LastName et al.`
- Sections as `## Heading` (H2)
- Figures as Obsidian wikilinks `![[filename.png]]` with italic caption on next line
- Failed images → `![[fig_missing.png]]` with HTML comment
- Filename sanitization: strip `<>:"/\|?*`, replace whitespace with `_`, truncate to 100 chars

Additions beyond web clipper:
- `paper-id` field in frontmatter (wiki's internal ID)
- `identifiers:` nested map (doi, arxiv, url) — matches the wiki's entity schema for dedup via `find_existing_paper_by_identifiers()`
- `year` as integer — extracted from `date` for paper-id generation

**Date normalization:** Publisher extractors must normalize raw date strings (e.g., IEEE's "Date of Publication: 15 March 2021") to ISO format `YYYY-MM-DD`. If only a year is available, use `YYYY-01-01`. If the date is completely unparseable, set `date` to empty string and `year` to `None` — the paper-id generator falls back to `0000` for the year component.

## Paper-ID Generation

The `paper-id` is the directory name and Obsidian filename. Algorithm (transcribed from `scripts/academic_wiki_lib/paper_id.py`):

0. **Manual fold** — before any normalization, transliterate characters that don't decompose under NFKD: `ø→o`, `æ→ae`, `œ→oe`, `ß→ss`, `ð→d`, `þ→th`, `ł→l` (and uppercase variants)
1. **Last name** — first author's last name → apply manual fold → NFKD normalize → strip combining marks → lowercase → strip all non-alphanumeric characters (not replace with hyphens)
2. **Year** — publication year as integer
3. **First meaningful word** — first word of the title after splitting on non-alphanumeric runs, skipping stop words (`a`, `an`, `the`, `on`, `of`, `for`, `with`) and pure-digit tokens → apply the same fold+strip pipeline
4. Combine as `{lastname}-{year}-{word}` (e.g., `vaswani-2017-attention`)

Example: author "Søndergaard", year 2024, title "The Optimal Control" → `sondergaard-2024-optimal`

**Collision resolution:** If `{wiki_path}/wiki/papers/{paper-id}.md` already exists, append a numeric suffix: `vaswani-2017-attention-2`, `vaswani-2017-attention-3`, etc. (checks `wiki/papers/` not `raw/papers/`, matching `resolve_collision` in `paper_id.py`)

This reuses the wiki plugin's `paper_id.py` from `scripts/academic_wiki_lib/` directly — not a reimplementation.

## Identifier Detection

`identifier.py` uses regex patterns:

```python
DOI_PATTERN = r"^10\.\d{4,9}/[^\s]+$"
ARXIV_PATTERN = r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+/\d{7})$"
ARXIV_URL_PATTERN = r"arxiv\.org/(abs|html|pdf)/(.+?)(/|$)"
DOI_URL_PATTERN = r"doi\.org/(10\.\d{4,9}/[^\s]+)"
```

Detection pipeline:
1. Strip known prefixes first: `arXiv:`, `arxiv:`, `doi:` → extract the raw ID
2. Try URL patterns (arXiv URL, DOI URL) → extract embedded ID
3. Try raw ID patterns (DOI, arXiv) against the stripped input
4. If no match → return "unknown" type

## Error Handling

- **Browser fallback:** Automatic Playwright → Selenium per-publisher. Reports which backend succeeded.
- **Unsupported publisher:** DOI redirect lands on unknown domain → error: "Publisher {domain} not supported"
- **Rate limiting:** Semantic Scholar — exponential backoff, max 5 retries
- **Image failures:** Mark figure as failed, continue extraction, note in HTML comment
- **Total failure:** Both backends fail → return error dict with `{ error, identifier, partial_metadata }`. No files are written to disk. The caller can use partial metadata (title, authors from `meta` tags) to display a useful error message.

## Testing Strategy

- **Unit tests per publisher:** Saved HTML fixtures → run extractor → assert metadata/sections/figures match expected
- **Unit tests for `markdown.py`:** Structured data in → assert output matches web clipper format
- **Unit tests for `identifier.py`:** DOI patterns, arXiv patterns, URL forms, edge cases
- **Integration test:** Mock browser backend → full `download_paper` pipeline end-to-end
- **No live publisher tests in CI** (flaky, rate-limited) — manual test script for spot-checking

## Dependencies

```
fastmcp>=3.1.1
playwright
selenium
undetected-chromedriver
selenium-stealth
requests
```

Python >=3.13.
