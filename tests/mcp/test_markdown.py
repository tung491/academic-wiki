from academic_wiki_mcp.markdown import to_markdown, format_inline_author
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


def test_format_inline_author_multiple():
    assert format_inline_author(["Ashish Vaswani", "Noam Shazeer"]) == "Vaswani et al."


def test_format_inline_author_single():
    assert format_inline_author(["John Smith"]) == "Smith"


def test_format_inline_author_empty():
    assert format_inline_author([]) == ""


def test_to_markdown_frontmatter(sample_metadata, sample_sections, sample_figures):
    md = to_markdown(sample_metadata, sample_sections, sample_figures,
                     paper_id="vaswani-2017-attention")
    assert "title: \"Attention Is All You Need\"" in md
    assert "inline_author: \"Vaswani et al.\"" in md
    assert "paper-id: \"vaswani-2017-attention\"" in md
    assert "  doi: \"10.48550/arXiv.1706.03762\"" in md
    assert "  arxiv: \"1706.03762\"" in md
    assert "year: 2017" in md
    assert "venue: \"NeurIPS 2017\"" in md


def test_to_markdown_sections(sample_metadata, sample_sections, sample_figures):
    md = to_markdown(sample_metadata, sample_sections, sample_figures,
                     paper_id="vaswani-2017-attention")
    assert "## Abstract" in md
    assert "We propose the Transformer." in md
    assert "## 1. Introduction" in md


def test_to_markdown_figure_wikilink(sample_metadata, sample_sections, sample_figures):
    md = to_markdown(sample_metadata, sample_sections, sample_figures,
                     paper_id="vaswani-2017-attention")
    assert "![[fig1.png]]" in md
    assert "*Figure 1: Architecture*" in md


def test_to_markdown_failed_figure():
    meta = Metadata(title="T", authors=["A B"], abstract="", doi="", arxiv=None,
                    url="", date="", year=None, venue="", keywords=[])
    sections = [Section(heading="S", content=[
        ContentBlock(type="figure", figure_id="f1"),
    ])]
    figures = [Figure(id="f1", url="x", filename="fig1.png", caption="Cap", failed=True)]
    md = to_markdown(meta, sections, figures, paper_id="test-id")
    assert "![[fig_missing.png]]" in md
    assert "<!-- Image download failed for: fig1.png -->" in md
    assert "*Cap*" in md


def test_to_markdown_no_optional_fields():
    meta = Metadata(title="T", authors=[], abstract="", doi="", arxiv=None,
                    url="", date="", year=None, venue="", keywords=[])
    md = to_markdown(meta, [], [], paper_id="test-id")
    assert "title: \"T\"" in md
    assert "authors:" not in md
    assert "doi:" not in md
