# DOI → BibTeX Tool — Design Spec

**Date:** 2026-04-19
**Component:** `academic_wiki_mcp`
**Status:** Draft (awaiting approval)

## 1. Goal

Add an MCP tool to `academic_wiki_mcp` that accepts a DOI and a `paper_id`, and returns a ready-to-write BibTeX entry whose citation key equals `paper_id`. The tool serves the wiki's per-paper `raw/bib/<paper-id>.bib` convention, replacing the current "stub `@misc{...}` with `bib-incomplete: true`" workflow when a real BibTeX source is available.

## 2. Non-Goals

- **No automatic file writing.** The tool returns the BibTeX text as a string. Caller decides whether to write `raw/bib/<paper-id>.bib`, splice into a draft, etc.
- **No `download_paper` integration.** The `download_paper` tool is unchanged; auto-populating bib files during ingest is a separate, future change.
- **No paper-id generation.** The caller has already chosen `paper_id` (typically via `scripts/academic_wiki_lib/paper_id.py:generate_paper_id`). The tool only stamps it onto the BibTeX.
- **No multi-DOI batch input.** One DOI per call. Callers loop if needed.
- **No format alternatives** (CSL-JSON, RIS, etc.). BibTeX only.

## 3. Underlying Mechanism

Per the [Project THOR documentation](https://project-thor.readme.io/docs/accessing-doi-metadata), DOI metadata is retrieved via **content negotiation** against the DOI resolver. The concrete request is:

```
GET https://doi.org/{doi}
Accept: application/x-bibtex; charset=utf-8
User-Agent: academic-wiki-mcp/1.0
```

This works for any DOI registered with Crossref, DataCite, mEDRA, or any other RA participating in content negotiation. No authentication, no rate limit beyond reasonable use.

When content negotiation fails (~5–10% of DOIs in practice — older publishers, non-Crossref DOIs, transient errors), the tool falls back to **Semantic Scholar** (`api.semanticscholar.org/graph/v1/paper/DOI:{doi}`). The project already has S2 client code wired up in `tools/discovery.py`; we extract it for reuse.

## 4. Architecture & File Layout

```
academic_wiki_mcp/
  s2_client.py          # NEW — extracted S2 helpers + new get_paper_by_doi
  bibtex.py             # NEW — pure logic (parse, key rewrite, build from S2)
  tools/
    bibtex.py           # NEW — MCP tool: doi_to_bibtex(doi, paper_id)
    discovery.py        # MODIFIED — import S2 helpers from s2_client
  server.py             # MODIFIED — add `bibtex` to the tools import line
tests/mcp/
  test_bibtex.py        # NEW — unit + mocked integration tests
```

**Why split root `bibtex.py` from `tools/bibtex.py`:** matches the project's existing convention. Root modules (`models.py`, `markdown.py`, `identifier.py`) hold pure logic. `tools/*.py` are thin MCP wrappers. Pure logic is unit-testable without mocking the network or the FastMCP decorator.

**Dependencies:** none new. `requests` is already a dependency.

## 5. Components & Signatures

### 5.1 `s2_client.py` (new)

Holds Semantic Scholar API helpers shared between `tools/discovery.py` and `tools/bibtex.py` (via the new module-level fallback).

```python
S2_GRAPH = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,authors,year,venue,abstract,externalIds,citationCount"

def _headers() -> dict[str, str]:
    """Returns {x-api-key: ...} if SEMANTIC_SCHOLAR_API_KEY is set, else {}."""

def _s2_get(url: str, params: dict | None = None,
            max_retries: int = 5) -> requests.Response | None:
    """GET with exponential backoff on 429/500/502/503. Returns response (200 or
    404) or None on exhaustion. Raises on other 4xx."""

def _normalize_s2_paper(p: dict) -> dict:
    """Normalize raw S2 paper dict to {paperId, title, authors[list[str]], year,
    venue, abstract, doi, arxiv, citationCount}."""

def get_paper_by_doi(doi: str) -> dict | None:
    """Fetch a paper by DOI from S2 Graph API. Returns normalized dict or None."""
```

`_headers`, `_s2_get`, `_normalize_s2_paper` are **moved** from `discovery.py` (no behavior change). `get_paper_by_doi` is new.

### 5.2 `bibtex.py` (new, pure logic)

```python
def parse_first_entry(bibtex_text: str) -> dict:
    """Parse the first @type{key, ...} entry. Returns
    {'type': str, 'key': str, 'fields': dict[str, str]}.
    Tolerates loose whitespace and nested braces in field values."""

def rewrite_citation_key(bibtex_text: str, paper_id: str) -> str:
    """Replace the citation key inside the first @type{KEY, ...} with paper_id.
    Preserves everything else verbatim. Raises ValueError if no @type{key,
    pattern is found (caller treats as a signal to fall back)."""

def build_from_metadata(meta: dict, paper_id: str) -> tuple[str, str]:
    """Construct a BibTeX entry from a normalized S2-shaped dict.

    Entry-type heuristic (case-insensitive on `meta['venue']`):
      - matches r"Proceedings|Conference|Symposium|Workshop|ICCV|CVPR|NeurIPS|ICML"
        → @inproceedings, field name `booktitle`
      - non-empty venue → @article, field name `journal`
      - empty venue → @misc, no booktitle/journal

    Authors are joined with ' and '.

    Always emits: title, author, year, doi (when present).
    Skips empty fields silently.

    Returns (bibtex_text, entry_type) — entry_type is one of
    "article" | "inproceedings" | "misc".

    Raises ValueError if title or year are missing (caller treats as
    'incomplete metadata')."""
```

### 5.3 `tools/bibtex.py` (new MCP wrapper)

```python
@mcp.tool()
async def doi_to_bibtex(doi: str, paper_id: str) -> dict:
    """Fetch BibTeX metadata for a DOI and return an entry keyed by paper_id.

    Tries doi.org content negotiation (Accept: application/x-bibtex). On
    failure, falls back to Semantic Scholar metadata and synthesizes a
    BibTeX entry.

    Returns:
      {"bibtex": "<entry text>",
       "source": "doi.org" | "semantic_scholar",
       "entry_type": "article" | "inproceedings" | "misc"}
      or {"error": "...", "doi": doi} on total failure.
    """
```

### 5.4 `tools/discovery.py` (modified)

- Remove the local definitions of `S2_GRAPH`, `S2_RECS`, `S2_FIELDS`, `_headers`, `_s2_get`, `_normalize_s2_paper`.
- Import them from `academic_wiki_mcp.s2_client`.
- Existing tools (`semantic_scholar_search`, `discover_related`) and helpers (`_search`, `_references`, `_citations`, `_recommendations`, `_resolve_s2_id`) keep their behavior. Only the import lines change.
- `S2_RECS` (recommendations endpoint) stays in `discovery.py` — it's only used there.

### 5.5 `server.py` (modified)

```python
from academic_wiki_mcp.tools import download, discovery, bibtex  # noqa: F401
```

## 6. Data Flow

### 6.1 Happy path (doi.org returns BibTeX)

```
1. Agent calls doi_to_bibtex(doi="10.1109/...", paper_id="vaswani2017attention")
2. tools/bibtex.py validates inputs (DOI matches ^10\., paper_id non-empty)
3. GET https://doi.org/{doi}
     headers = {"Accept": "application/x-bibtex; charset=utf-8",
                "User-Agent": "academic-wiki-mcp/1.0"}
     allow_redirects=True, timeout=15
4. If status 200 AND (Content-Type contains "bibtex" OR body starts with "@"):
     raw = resp.text
     entry_type = parse_first_entry(raw)["type"]
     out = rewrite_citation_key(raw, paper_id)
     return {"bibtex": out, "source": "doi.org", "entry_type": entry_type}
5. Else: fall through to §6.2.
```

### 6.2 Fallback path (Semantic Scholar)

```
1. meta = s2_client.get_paper_by_doi(doi)
2. If meta is None:
     return {"error": "DOI not found in doi.org or Semantic Scholar", "doi": doi}
3. try:
     out, entry_type = bibtex.build_from_metadata(meta, paper_id)
   except ValueError as e:  # missing title/year
     return {"error": f"S2 metadata incomplete: {e}",
             "doi": doi, "partial": meta}
4. return {"bibtex": out, "source": "semantic_scholar",
           "entry_type": entry_type}
```

### 6.3 Triggers for fallback

doi.org → fallback when ANY of:
- Status 404 (DOI not registered for content negotiation)
- Status 406 (format not acceptable)
- Status 503 / 5xx (transient)
- Network exception (`requests.RequestException`, `Timeout`, etc.)
- Status 200 but body doesn't start with `@`
- Status 200, parses, but `rewrite_citation_key` raises (no `@type{key,` found)

## 7. Error Handling

| Failure | doi.org path | Fallback path | Final return |
|---|---|---|---|
| `doi` empty / not matching `^10\.` | — | — | `{"error": "invalid DOI", "doi": doi}` |
| `paper_id` empty | — | — | `{"error": "paper_id is required"}` |
| doi.org timeout (15s) | log WARNING + fallback | run | depends on fallback |
| doi.org 404/406/503 | log WARNING + fallback | run | depends on fallback |
| doi.org 200, body not BibTeX | log WARNING + fallback | run | depends on fallback |
| `rewrite_citation_key` raises | log WARNING + fallback | run | depends on fallback |
| S2 returns None | — | — | `{"error": "DOI not found in doi.org or Semantic Scholar", "doi": doi}` |
| S2 metadata missing title or year | — | — | `{"error": "S2 metadata incomplete: ...", "doi": doi, "partial": meta}` |
| Unexpected exception in either path | caught | caught | `{"error": "<class>: <msg>", "doi": doi}` |

**Logging:** stdlib `logging`, module-level `logger = logging.getLogger(__name__)`. WARNING level on fallback (so users can audit how often doi.org succeeds); DEBUG on the happy path. No `print` statements.

**Retry behavior:**
- doi.org: single attempt, 15s timeout. No internal retries — failures fall straight to S2.
- S2: existing `_s2_get` retry logic (5 attempts, exponential backoff on 429/500/502/503).

**The tool never raises.** All exceptions are caught at the `@mcp.tool()` boundary and converted to the `{"error": ...}` shape. Callers can rely on a dict return for both success and failure.

## 8. Testing

New file: `tests/mcp/test_bibtex.py`. Style matches `tests/mcp/test_discovery.py` — `pytest`, `pytest-asyncio`, `unittest.mock.patch` for HTTP, no live network.

### 8.1 Pure-logic unit tests (no network)

- `test_parse_first_entry_basic` — `@article{Smith_2020, title={Foo}, year={2020}}` parses to `{"type": "article", "key": "Smith_2020", "fields": {"title": "Foo", "year": "2020"}}`
- `test_parse_first_entry_handles_inproceedings_with_braces` — multiline entry, nested braces in title
- `test_rewrite_citation_key_replaces_first_match` — rest of body byte-identical
- `test_rewrite_citation_key_preserves_other_at_signs` — `@article{x, note={foo@bar.com}}` only first `@` rewritten
- `test_rewrite_citation_key_no_match_raises` — body without `@type{key,` raises `ValueError`
- `test_build_from_metadata_inproceedings` — venue contains "Proceedings" → `@inproceedings`, `booktitle`
- `test_build_from_metadata_article` — plain venue → `@article`, `journal`
- `test_build_from_metadata_misc_no_venue` — empty venue → `@misc`
- `test_build_from_metadata_authors_joined_with_and` — `["A B", "C D"]` → `"A B and C D"`
- `test_build_from_metadata_omits_empty_fields` — no abstract present → no abstract field
- `test_build_from_metadata_raises_when_title_missing` — guard
- `test_build_from_metadata_raises_when_year_missing` — guard

### 8.2 MCP-tool integration tests (mocked `requests.get`)

- `test_doi_to_bibtex_doi_org_happy_path` — mock 200 + `@article{x, ...}` body → `source == "doi.org"`, key rewritten
- `test_doi_to_bibtex_falls_back_on_404` — mock doi.org 404, mock S2 200 with metadata → `source == "semantic_scholar"`, valid bibtex
- `test_doi_to_bibtex_falls_back_on_non_bibtex_body` — mock 200 with HTML body → fallback path
- `test_doi_to_bibtex_falls_back_on_timeout` — mock `requests.get` raising `Timeout` → fallback path
- `test_doi_to_bibtex_total_failure` — both doi.org and S2 fail → `{"error": ..., "doi": ...}`
- `test_doi_to_bibtex_invalid_doi_returns_error_without_network` — `doi="not-a-doi"` → error, `requests.get` never called
- `test_doi_to_bibtex_empty_paper_id_returns_error` — guard
- `test_doi_to_bibtex_s2_incomplete_metadata` — S2 returns paper without `year` → `{"error": "S2 metadata incomplete: ...", "partial": meta}`

### 8.3 Regression test

- Re-run `tests/mcp/test_discovery.py` after the `_s2_get`/`_normalize_s2_paper` extraction. Imports change to `academic_wiki_mcp.s2_client` but test patches must follow (`patch("academic_wiki_mcp.s2_client.requests.get", ...)` or `patch("requests.get", ...)` if module-level). Existing tests should keep passing.

### 8.4 Out of scope

- No live-network smoke test by default. (A `@pytest.mark.live` gated test could be added later if real-DOI assurance becomes important.)

## 9. Open Questions

None. All decisions resolved during brainstorming:
- Single-purpose standalone tool (no auto-write, no `download_paper` integration).
- Caller supplies `paper_id`; tool always rewrites the citation key to it.
- doi.org content negotiation primary; Semantic Scholar fallback.
- No new dependencies.

## 10. Future Work (out of scope)

- Wire `doi_to_bibtex` into `download_paper` so newly-ingested papers get a populated `raw/bib/<paper-id>.bib` automatically.
- Add a `bibtex_format` parameter to support CSL-JSON or RIS for callers that want structured metadata.
- Add a `@pytest.mark.live` smoke test against a small set of known-good and known-flaky DOIs.
- Cache successful doi.org responses to avoid hammering the resolver during bulk ingest.
