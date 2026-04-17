from __future__ import annotations
from pathlib import Path

import pytest

from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


@pytest.fixture
def tmp_wiki(tmp_path):
    wiki = tmp_path / "test-wiki"
    for sub in [
        "raw/papers", "raw/extracts", "raw/bib", "raw/figures", "raw/notes",
        "wiki/papers", "wiki/concepts", "wiki/methods", "wiki/open-problems",
        "wiki/claims", "wiki/results", "wiki/authors", "wiki/venues", "wiki/queries",
        "outputs/reports", "outputs/bib",
    ]:
        (wiki / sub).mkdir(parents=True, exist_ok=True)
    (wiki / "wiki/index.md").write_text("# test-wiki Wiki Index\n")
    (wiki / "log.md").write_text("# test-wiki Wiki Log\n")
    return wiki


@pytest.fixture
def sample_metadata():
    return Metadata(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
        abstract="We propose the Transformer.",
        doi="10.48550/arXiv.1706.03762",
        arxiv="1706.03762",
        url="https://arxiv.org/html/1706.03762",
        date="2017-06-12",
        year=2017,
        venue="NeurIPS 2017",
        keywords=["transformer", "attention"],
    )


@pytest.fixture
def sample_sections():
    return [
        Section(heading="Abstract", content=[
            ContentBlock(type="paragraph", text="We propose the Transformer."),
        ]),
        Section(heading="1. Introduction", content=[
            ContentBlock(type="paragraph", text="Sequence models dominate."),
            ContentBlock(type="figure", figure_id="fig1"),
        ]),
    ]


@pytest.fixture
def sample_figures():
    return [
        Figure(id="fig1", url="https://example.com/fig1.png",
               filename="fig1.png", caption="Figure 1: Architecture"),
        Figure(id="fig2", url="https://example.com/fig2.png",
               filename="fig2.png", caption="", failed=True),
    ]


FIXTURES_DIR = Path(__file__).parent / "fixtures"
