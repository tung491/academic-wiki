from academic_wiki_mcp.models import Metadata, ContentBlock, Section, Figure


def test_metadata_creation(sample_metadata):
    assert sample_metadata.title == "Attention Is All You Need"
    assert sample_metadata.year == 2017
    assert sample_metadata.arxiv == "1706.03762"


def test_figure_defaults():
    fig = Figure(id="f1", url="http://x.com/f.png", filename="f1.png", caption="")
    assert fig.data is None
    assert fig.failed is False


def test_content_block_paragraph():
    cb = ContentBlock(type="paragraph", text="Hello")
    assert cb.figure_id is None


def test_content_block_figure():
    cb = ContentBlock(type="figure", figure_id="fig1")
    assert cb.text is None
