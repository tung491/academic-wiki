"""Shared pytest fixtures."""
from pathlib import Path

import pytest


@pytest.fixture
def tmp_wiki(tmp_path):
    """A fresh empty wiki directory tree per test."""
    wiki = tmp_path / "academic"
    for sub in [
        "raw/papers", "raw/extracts", "raw/bib", "raw/figures", "raw/notes",
        "wiki/papers", "wiki/concepts", "wiki/methods", "wiki/open-problems",
        "wiki/claims", "wiki/results", "wiki/authors", "wiki/venues", "wiki/queries",
        "outputs/reports", "outputs/bib",
    ]:
        (wiki / sub).mkdir(parents=True, exist_ok=True)
    (wiki / "wiki/index.md").write_text("# academic Wiki Index\n")
    (wiki / "log.md").write_text("# academic Wiki Log\n")
    return wiki


@pytest.fixture
def sample_paper_content():
    """A tiny paper extract for ingest/compile tests."""
    return """---
paper-id: vaswani2017attention
source-path: raw/papers/vaswani2017attention.pdf
source-sha: abc123
source-type: pdf
source-url: https://arxiv.org/abs/1706.03762
extractor: ocr-papers-to-latex
extracted-at: 2026-04-16T10:00:00Z
ocr-used: false
extract-status: complete
---
# Attention Is All You Need

We propose the Transformer, a model based entirely on attention.

## References
1. Bahdanau, D. et al. Neural Machine Translation. 2014.
2. Cho, K. et al. Learning Phrase Representations. 2014.
"""
