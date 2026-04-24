# S2 Auto-Stub on Query — Design Spec

**Date:** 2026-04-24
**Component:** `semantic_scholar_mcp` + `academic_wiki_mcp` (both servers' S2 tools) + `scripts/academic_wiki_lib`
**Status:** Draft (awaiting spec review + user approval)

## 1. Goal

Every Semantic Scholar discovery call (keyword search, DOI lookup, related-paper discovery) automatically writes a lightweight clipper-compatible stub for each result into the active wiki's `raw/papers/` directory. The next `wiki ingest` batch-scan picks the stubs up automatically, assigns paper-ids, dedupes against existing pages, and `wiki compile` builds wiki pages from the abstract+metadata. No PDFs are fetched; no user action is required between the S2 query and the next `wiki ingest`/`wiki compile`.

The result: the wiki accumulates a paper-by-paper "discovery cache" of every S2 result the user has ever seen, deduplicated against existing entries, available for future querying via `wiki query`, citation export via `wiki export-bibtex`, etc.

## 2. Non-Goals

- **No automatic PDF fetching.** S2 returns metadata only; full extraction stays a deliberate `wiki ingest <doi>` action by the user.
- **No changes to `download_paper` or any other wiki MCP tool.** Only the three S2 discovery tools gain the side effect.
- **No changes to the `wiki ingest` batch-scan flow.** Stubs use the existing "no `paper-id` OR `extract-status` not `complete`" filter — `pending-s2` already qualifies as "not complete."
- **No new wiki commands.** No `wiki ingest --from-queue` or similar; the existing batch-scan is the entry point.
- **No lockfile coordination.** Stub writes are atomic per-paper dir creations independent of the wiki's lockfile (see §6).
- **No backwards compatibility shim** for stubs created before this spec — none exist.
- **No marketplace/plugin metadata changes.**
- **No Obsidian-side UX** (the user discovers stubs via the next `wiki ingest`/`wiki compile`).

## 3. Background

Two MCP servers in this repository expose S2 discovery tools:

- `semantic_scholar_mcp/tools/discovery.py` — standalone server, three tools: `semantic_scholar_search`, `get_paper_by_doi`, `discover_related`.
- `academic_wiki_mcp/tools/discovery.py` — integrated server, two tools: `semantic_scholar_search`, `discover_related`. (`get_paper_by_doi` exists as a plain function in `academic_wiki_mcp/s2_client.py` but isn't registered as a tool here.) **This spec adds a third tool** `get_paper_by_doi` to the integrated server's tool surface (decorating the existing function with `@mcp.tool()` and adding the auto-stub hook), so the change to `academic_wiki_mcp` is "register a new tool + hook all three" not "hook the two existing tools."

Both servers' S2 code is near-duplicate (per the standalone-extraction spec `2026-04-24-semantic-scholar-mcp-design.md`).

The wiki ingestion pipeline (see `skills/wiki/SKILL.md` `ingest` section) already handles clipper-style directories under `raw/papers/<dirname>/` containing one `.md` file with frontmatter. The batch-scan mode (`wiki ingest` with no argument) walks `raw/papers/*/`, filters to unprocessed dirs, and processes each via the standard pipeline (paper-id generation, byte-level + identifier-level dedup, frontmatter merge, optional figures symlink).

Per the user's project memory (`feedback_dedup_marking.md`), the unprocessed filter treats `extract-status: duplicate` as "skip." This spec adds `extract-status: pending-s2` as a value the filter must continue to accept as "process." No filter changes are required: the existing filter is "no `paper-id` OR `extract-status` not `complete`," which includes `pending-s2`.

## 4. Architecture

### 4.1 New module

```
scripts/academic_wiki_lib/
  s2_stub.py           # NEW — write_s2_stubs(), resolve_default_wiki(),
                       # _compute_slug() (private), schema constants
tests/wiki/
  test_s2_stub.py      # NEW — unit tests
```

### 4.2 Modified files

```
semantic_scholar_mcp/tools/discovery.py   # MODIFIED — add hook to all 3 tools
academic_wiki_mcp/tools/discovery.py      # MODIFIED — add hook to all 3 tools
                                          # (registers get_paper_by_doi as a new MCP tool)
academic_wiki_lib/  (clipper handler)     # MODIFIED (1-line) — preserve
                                          # extractor: s2-stub when promoting
                                          # (see §5.4)
```

### 4.3 Public surface of `s2_stub.py`

```python
def write_s2_stubs(papers: list[dict], wiki_root: str | None) -> dict:
    """Write each paper as a clipper-style stub dir under <wiki_root>/raw/papers/.

    Each input paper is a normalized S2 dict (from _normalize_s2_paper) with keys:
      paperId, title, authors, year, venue, abstract, doi, arxiv, citationCount, ...

    Returns a summary dict (never raises):
      {
        "wiki_root": str | None,
        "written": int,                    # newly-created stubs
        "skipped_existing": int,           # slug already present on disk
        "skipped_no_identifier": int,      # paper has no DOI, arxiv, or paperId
        "skipped_no_wiki": bool,           # wiki_root is None or doesn't exist
        "failed": int,                     # per-paper write errors
      }
    """

def resolve_default_wiki(start_cwd: str | None = None) -> str | None:
    """Resolve the active wiki root.

    1. If start_cwd is provided, walk up via find_active_wiki(start_cwd). If found, return it.
    2. Read env var ACADEMIC_WIKI_DEFAULT. If set and the path has wiki markers, return it.
    3. Return None.
    """
```

### 4.4 Hook integration pattern

Each S2 tool in both servers gets the same two-line hook wrapping its return value:

```python
@mcp.tool()
async def semantic_scholar_search(query: str, ...) -> list[dict]:
    results = await _search(...)
    try:
        from academic_wiki_lib.s2_stub import write_s2_stubs, resolve_default_wiki
        write_s2_stubs(results, wiki_root=resolve_default_wiki(os.getcwd()))
    except Exception:
        pass  # never fail the tool because of the side effect
    return results
```

Per-tool variants:

- `semantic_scholar_search` → hook on `results` (already a list).
- `discover_related` → hook on `combined[:limit]` (the `related` list, not the wrapper dict).
- `get_paper_by_doi` → hook on `[result]` if non-`None`, else skip the hook entirely.

For the standalone `semantic_scholar_mcp`, `academic_wiki_lib` is not on the import path. The hook adds a `sys.path.insert` shim mirroring `academic_wiki_mcp/tools/download.py:19` (the single-line `sys.path.insert` that lets that file import `academic_wiki_lib.paper_id`):

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
```

This works as long as the standalone server is run from inside the `academic_wiki` repo. When the standalone is later extracted to its own repo (per the standalone-extraction spec's "Future Work"), the shim becomes a no-op fallback (the import will fail, the outer `try/except` swallows it, and S2 stubs simply aren't written).

### 4.5 Failure semantics summary

| Condition | Behavior |
|---|---|
| Active wiki not found (no `start_cwd` match, no env var) | `write_s2_stubs` returns `skipped_no_wiki: True`. Tool returns S2 results normally. |
| Hook raises (import error, programming bug) | Outer `try/except` in the tool swallows it. Tool returns S2 results normally. |
| Per-paper write error (permissions, disk full) | `write_s2_stubs` increments `failed`, continues to next paper, returns full summary. Tool returns S2 results normally. |
| `S2_STUB_DEBUG=1` env var set | `write_s2_stubs` writes a one-line stderr summary on every call (counts of written/skipped/failed). |

## 5. Stub schema

### 5.1 File layout

For each result, the stub writer creates:

```
<wiki_root>/raw/papers/<slug>/
└── <slug>.md
```

`<slug>` is computed deterministically from the paper's identifiers (see §5.5).

### 5.2 Frontmatter

```yaml
---
title: "Attention Is All You Need"
authors:
  - Ashish Vaswani
  - Noam Shazeer
year: 2017
venue: "Advances in Neural Information Processing Systems"
doi: "10.48550/arXiv.1706.03762"
arxiv: "1706.03762"
s2-paper-id: "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
citation-count: 95234
source-url: "https://doi.org/10.48550/arXiv.1706.03762"
extractor: s2-stub
extract-status: pending-s2
extracted-at: "2026-04-24T18:42:11Z"
queried-at: "2026-04-24T18:42:11Z"
---
```

Field rules:

- **No `paper-id`** — assigned by the next `wiki ingest` batch-scan run (so the batch-scan filter picks the stub up).
- **`extract-status: pending-s2`** — sentinel value distinct from `complete`/`duplicate`. The existing batch-scan filter "no `paper-id` OR `extract-status` not `complete`" already includes `pending-s2`; no filter changes needed.
- **`extractor: s2-stub`** — sentinel value. Lets future code/lint audit S2-only entries (e.g., warn on `s2-stub` older than 30 days that hasn't been upgraded).
- **`source-url`** priority: `https://doi.org/<doi>` → `https://arxiv.org/abs/<arxiv>` → `https://www.semanticscholar.org/paper/<s2-paper-id>` → omitted if all three are missing (paper would be skipped per §5.5 anyway).
- **`citation-count`** stored for future sortability/lint signals; not used by ingest or compile.
- **`queried-at`** records when the user's S2 search happened; same as `extracted-at` initially. Reserved for a future "touch on re-query" feature; not modified by ingest.
- **Empty/missing S2 fields are omitted** from frontmatter (not written as `null` or empty string) — keeps the YAML clean and round-trips through `read_frontmatter` without spurious keys.

### 5.3 Body

```markdown
## Abstract

The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...
```

If S2 returns an empty/missing `abstract`, the body is just `## Abstract\n\n*(no abstract available from Semantic Scholar)*\n` — leaves a visible placeholder so a `wiki compile` of the stub doesn't silently produce a paper page with no body content.

No `images/` subdirectory is created — S2 does not provide figures, and the clipper handler skips its symlink step gracefully when `images/` is absent.

### 5.4 What `wiki ingest` does to the stub

No code changes to the ingest skill itself. Existing flow:

1. Batch scan finds `raw/papers/<slug>/<slug>.md` (no `paper-id` in frontmatter → unprocessed).
2. Pipeline computes paper-id from title/authors/year (e.g. `vaswani2017attention`).
3. Dedup pass 2 (identifier-level): if DOI/arXiv matches an existing wiki page, merge identifiers and exit (the stub stays in place but is marked deduped — see open issue O-1 below).
4. Otherwise: merges in `paper-id`, `source-sha`, sets `extract-status: complete`, computes `source-sha` from the stub `.md` itself.

**One change required to the existing ingest skill.** The clipper handler is **not** a Python module — it is the `Clipper directory ingest` block in `skills/wiki/SKILL.md` (executed by the LLM running the `wiki ingest` skill). Step 5 of that block currently writes:

```yaml
extractor: obsidian-clipper
```

unconditionally. The change for this spec:

> When merging fields back into the stub frontmatter, **do not overwrite `extractor` if it is already set to `s2-stub`**. Today's behavior overwrites with `obsidian-clipper`. The new behavior preserves `s2-stub` so future audits can identify S2-only entries.

This is a SKILL.md edit (a one-bullet conditional rule under step 5 of the clipper handler), not a Python code change. The implementation plan will craft the exact wording to add to the skill.

### 5.5 Slug naming (deterministic, idempotent)

Priority order, first match wins:

1. **DOI present** → `s2-doi-<sanitized-doi>`
   - Sanitize: lowercase; replace `/` with `_`; replace any non-`[a-z0-9._-]` with `-`.
   - Truncate at 100 chars (some DOIs are very long; collisions vanishingly rare after 100 chars).
   - Example: `10.1109/JIOT.2024.123456` → `s2-doi-10.1109_jiot.2024.123456`.

2. **arXiv ID present** (no DOI) → `s2-arxiv-<arxiv-id>`
   - Strip leading `arxiv:` prefix if present.
   - Strip version suffix (`v3`, `v12`) so `1706.03762v5` and `1706.03762` map to the same dir.
   - Example: `1706.03762` → `s2-arxiv-1706.03762`.

3. **S2 paperId present** (no DOI, no arXiv) → `s2-pid-<sha8>`
   - `sha8` = first 8 hex chars of `sha256(s2-paper-id)`.
   - Example: `204e3073870fae3d05bcbc2f6a8e263d9b72e776` → `s2-pid-a1b2c3d4`.

4. **No DOI, no arXiv, no S2 paperId** → skip writing the stub entirely; counted as `skipped_no_identifier`.

Why identifier-based slugs (not paper-id-style `vaswani2017attention`):

- Stable regardless of metadata-extraction quirks (S2's author list is sometimes "et al." which would mangle `lastname`).
- After ingest assigns the real `paper-id`, the slug stays distinct from the wiki page's basename — no collision between `raw/papers/s2-doi-.../` and `wiki/papers/vaswani2017attention.md`.
- The `s2-` prefix groups all S2-sourced dirs together in a directory listing.

## 6. Concurrency and dedup

### 6.1 Pre-write dedup

For each paper, in order:

1. Compute slug per §5.5. If `None`, increment `skipped_no_identifier`, continue.
2. Build `<wiki_root>/raw/papers/<slug>/`.
3. If the dir exists, increment `skipped_existing`, continue. (No stat-and-merge; the existing stub stays as-is.)
4. Else create the dir, write `<slug>.md.tmp`, then `os.rename` to `<slug>.md`. Increment `written`.

The atomic-rename pattern guarantees the next `wiki ingest` batch-scan never sees a partial file: it sees either no `.md` (and the "≥1 .md" filter skips the dir) or a complete `.md`.

### 6.2 No lockfile coordination

The stub writer does **not** acquire `<wiki_root>/.lock`. Justifications:

- Each stub write is an independent dir creation; no shared file mutation.
- Acquiring the lock would block during a long `wiki compile` run, hanging S2 searches. Bad UX.
- Worst-case race: a concurrent `wiki ingest` reads the dir between our `os.makedirs` and `os.rename`. The dir is empty, ingest's "find ≥1 `.md`" check skips it, and the next ingest run picks it up. Acceptable.
- A hypothetical race where two S2 queries write the same slug simultaneously: both `os.makedirs(exist_ok=True)` succeed; the second `os.rename` overwrites the first. Both results have identical content (same DOI, same metadata source) so the overwrite is semantically a no-op.

### 6.3 Inter-query idempotence

Re-running the same S2 query (same DOI in results) → same slug → second query's existence check skips. Stub frontmatter is not refreshed (no `queried-at` bump in v1). A future enhancement could touch `queried-at` to track "last-seen" but is out of scope.

### 6.4 Cross-tool idempotence

If the same paper is returned by `semantic_scholar_search` and later by `discover_related`, both write the same slug → second one skips. ✓

## 7. Wiki resolution

`resolve_default_wiki(start_cwd)`:

1. If `start_cwd` is provided, call `academic_wiki_lib.wiki_paths.find_active_wiki(start_cwd)` (walks up from `start_cwd` looking for `CLAUDE.md` + `wiki/`). If found, return it.
2. Read env var `ACADEMIC_WIKI_DEFAULT`. If set and the path resolves to a directory with `CLAUDE.md` + `wiki/`, return it.
3. Return `None`.

The MCP servers pass `os.getcwd()` as `start_cwd`. In practice the MCP process's CWD is wherever Claude Code launched, usually `~/Work/academic_wiki/` (no wiki markers); step 1 falls through and step 2 hits the env var. Auto-detect is a "free upgrade" for the case where Claude Code launches inside a vault dir.

Recommended user setup (documented in the plan, not enforced by code):

```bash
export ACADEMIC_WIKI_DEFAULT="$HOME/Documents/Obsidian Vault/03-Resources/academic"
```

## 8. Tests

### 8.1 Unit tests for `s2_stub.py`

Location: `tests/wiki/test_s2_stub.py` (new file; mirrors `tests/mcp/` for MCP-tool integration but lives under `tests/wiki/` because it tests a `scripts/academic_wiki_lib/` module).

1. **Slug generation** (`_compute_slug`):
   - DOI present → `s2-doi-<sanitized>` (case + slash + special-char tests).
   - DOI absent, arXiv with version → `s2-arxiv-<id-without-version>`.
   - DOI + arXiv both absent, S2 paperId → `s2-pid-<sha8>`.
   - All identifiers absent → returns `None`.
   - DOI longer than 100 chars → truncated correctly.

2. **`resolve_default_wiki`** (with `tmp_path` and `monkeypatch`):
   - Walks up to find wiki markers when `start_cwd` is inside a fixture wiki.
   - Falls back to `ACADEMIC_WIKI_DEFAULT` env var when CWD has no markers.
   - Returns `None` when neither resolves.
   - Skips invalid env-var paths (path doesn't exist or lacks markers).

3. **`write_s2_stubs`** (with `tmp_path` simulating a wiki root):
   - Writes one stub per paper with correct frontmatter.
   - Body contains `## Abstract\n\n<text>`.
   - Empty/missing abstract → placeholder string.
   - Atomic write: `<slug>.md.tmp` does not appear after success.
   - Re-running with same papers → `skipped_existing` count matches; no overwrites.
   - Mixed batch (new + existing + no-identifier) returns correct counts.
   - `wiki_root=None` → returns `skipped_no_wiki: True`; no filesystem ops.
   - `wiki_root` points to nonexistent path → same no-wiki return.
   - `raw/papers/` missing → created on first call.
   - Per-paper write failure (chmod 000) → other papers still succeed; `failed` counter increments.

4. **Frontmatter content** (round-trip via `read_frontmatter`):
   - Empty/missing S2 fields are omitted from the frontmatter (not written as `null` or empty string).
   - `source-url` priority: DOI → arXiv abs → S2 paper URL.
   - `extracted-at` and `queried-at` are valid ISO-8601 UTC strings.

### 8.2 Integration tests

Location: `tests/mcp/test_s2_auto_stub.py` (new) or extend existing `tests/mcp/` tests; the implementation plan decides based on existing fixture infrastructure.

5. **Hook fires on each tool** — for both MCP servers:
   - `semantic_scholar_search` → stubs written for each result (mock the S2 HTTP call).
   - `discover_related` → stubs written for `related` list (not the wrapper dict).
   - `get_paper_by_doi` → stub written for the single result (None case → no write).
   - Hook exception swallowed: monkeypatch `write_s2_stubs` to raise, assert tool still returns results.

6. **End-to-end stub → ingest** (one test, slow but high-value):
   - Run `write_s2_stubs` against a fake S2 result in a `tmp_path` wiki.
   - Run the existing `wiki ingest` batch-scan flow against the same wiki root.
   - Assert the resulting `wiki/papers/` page has the expected paper-id.
   - Assert `extractor: s2-stub` is preserved in the merged frontmatter (per §5.4).
   - Assert dedup pass 2 deduplicates if the same DOI is then ingested via `wiki ingest <doi>`.

### 8.3 Tests explicitly out of scope for v1

- Concurrent stub-write race conditions (the no-lockfile decision means we accept ingest might transiently see an empty dir; the atomic-rename argument in §6 covers correctness).
- Network behavior of S2 itself (stubs written from synthetic dicts; live API calls not exercised here).
- Performance / load testing.

## 9. Observability

- `S2_STUB_DEBUG=1` env var → `write_s2_stubs` writes a one-line stderr summary on every invocation. Format:
  ```
  [s2-stub] wiki=<wiki_root_or_NONE> written=N skipped_existing=M skipped_no_id=K failed=F
  ```
- No metrics, no log files. The user can inspect `<wiki_root>/raw/papers/s2-*` directly to see what's been cached.

## 10. Migration / rollout

- No data migration: this spec adds new behavior to existing tools. Existing wiki content is untouched.
- No feature flag: the hook is always on; if no wiki is resolved, it's a silent no-op.
- Removal: deleting the `try/except` block from each tool reverts the behavior fully. The `s2_stub.py` module can be deleted; existing stubs in `raw/papers/s2-*/` remain valid clipper-style dirs and will be processed normally by the next ingest run regardless.

## 11. Open issues / future work

**O-1: Stubs that get deduped at ingest stay in `raw/papers/`.** When dedup pass 2 matches an existing paper, the ingest pipeline currently exits without modifying the stub dir (per `skills/wiki/SKILL.md:215-217`). The stub becomes orphaned: it has no `paper-id`, so the next batch scan picks it up again, runs dedup, exits again. Memory `feedback_dedup_marking.md` covers a similar case for clipper dups via `extract-status: duplicate`. Resolution paths for v2:

- Apply the same `extract-status: duplicate` + `duplicate-of: <paper-id>` marking to S2 stubs that hit dedup pass 2.
- Or have ingest delete the stub dir on dedup-match (more aggressive; loses the discovery record).

For v1, accept the cosmetic re-scan cost. If it becomes annoying, add the dup-marking step.

**O-2: `queried-at` refresh on re-query.** Out of scope for v1 — would require reading + rewriting frontmatter on every `skipped_existing` case. Cheap but adds I/O.

**O-3: Sharing the schema with future S2-related tools** (e.g., a hypothetical `semantic_scholar_recommend_personal_library` tool). Schema constants in `s2_stub.py` are reusable; no extra design work needed now.

**O-4: When `semantic_scholar_mcp` is later extracted to its own repo**, the `sys.path.insert` shim becomes a no-op. The hook should fail gracefully (import error → outer `try/except` swallows → no stubs written). A standalone successor could ship its own minimal `s2_stub.py` clone if desired. Not blocking.
