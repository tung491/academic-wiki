# Mini-wiki integration fixture

A minimal hand-crafted wiki structure for integration tests that exercise
`academic_wiki_lib` primitives end-to-end. Tests build papers programmatically
using the `tmp_wiki` pytest fixture (see `tests/conftest.py`) rather than
checking binary files into the repo.

The goal is to verify that the composition of helpers (slug, paper_id,
source_sha, frontmatter, lockfile, wiki_paths, templates) produces correct
results when combined — NOT to test LLM content quality.

Agent-driven end-to-end smoke tests (actual ingest of arXiv papers, MCP calls,
etc.) are documented separately in `WALKTHROUGH.md` and Task 1.18.
