# Academic Wiki MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastMCP server that downloads academic papers from 8 publisher websites and discovers related work via Semantic Scholar, outputting Obsidian-flavored Markdown matching the academic_web_clipper format.

**Architecture:** Python FastMCP server with a browser abstraction layer (Playwright primary, stealth Selenium fallback), per-publisher extraction modules porting CSS selectors from the web clipper, and Semantic Scholar API integration for discovery. The server reuses `paper_id.py` from the existing wiki library.

**Tech Stack:** Python 3.13, FastMCP, Playwright, Selenium + undetected-chromedriver + selenium-stealth, requests

**Spec:** `docs/superpowers/specs/2026-04-17-academic-wiki-mcp-server-design.md`

**Reference implementation:** `academic_web_clipper/` (Chrome extension whose extraction patterns are ported)

---

## File Map

```
academic_wiki_mcp/
├── __init__.py              # FastMCP("AcademicWikiServer") singleton
├── server.py                # Entry point: imports tools, runs mcp
├── config.py                # WIKI_ROOT, SEMANTIC_SCHOLAR_API_KEY, browser prefs
├── models.py                # Metadata, ContentBlock, Section, Figure dataclasses
├── identifier.py            # detect(input) -> ("doi"|"arxiv"|"unknown", raw_id)
├── markdown.py              # to_markdown(metadata, sections, figures) -> str
├── browser.py               # Element ABC, BrowserBackend ABC, PlaywrightBackend, SeleniumBackend
├── tools/
│   ├── __init__.py
│   ├── download.py          # download_paper MCP tool
│   └── discovery.py         # semantic_scholar_search, discover_related MCP tools
└── publishers/
    ├── __init__.py           # PUBLISHERS list + find_publisher()
    ├── base.py               # BasePublisher ABC + meta-tag fallback helpers
    ├── arxiv.py
    ├── ieee.py
    ├── springer.py
    ├── sciencedirect.py
    ├── mdpi.py
    ├── wiley.py
    ├── tandfonline.py
    └── asce.py

tests/mcp/
├── __init__.py
├── conftest.py              # Shared fixtures: MockBrowser, sample HTML, tmp_wiki
├── test_identifier.py
├── test_markdown.py
├── test_models.py
├── test_browser.py
├── test_publisher_base.py
├── test_arxiv.py
├── test_ieee.py
├── test_springer.py
├── test_sciencedirect.py
├── test_mdpi.py
├── test_wiley.py
├── test_tandfonline.py
├── test_asce.py
├── test_download.py
├── test_discovery.py
└── fixtures/                # Saved HTML per publisher for deterministic tests
    ├── arxiv_sample.html
    ├── ieee_sample.html
    ├── springer_sample.html
    ├── sciencedirect_sample.html
    ├── mdpi_sample.html
    ├── wiley_sample.html
    ├── tandfonline_sample.html
    └── asce_sample.html
```

---

### Task 1: Project Scaffolding and Dependencies

**Files:**
- Create: `academic_wiki_mcp/__init__.py`
- Create: `academic_wiki_mcp/server.py`
- Create: `academic_wiki_mcp/config.py`
- Create: `academic_wiki_mcp/models.py`
- Create: `academic_wiki_mcp/tools/__init__.py`
- Create: `academic_wiki_mcp/publishers/__init__.py`
- Create: `tests/mcp/__init__.py`
- Create: `tests/mcp/conftest.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update pyproject.toml with MCP server dependencies**

Add optional dependency group `mcp` and adjust pythonpath:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.23",
]
mcp = [
    "fastmcp>=3.1.1",
    "playwright>=1.40",
    "selenium>=4.41.0",
    "undetected-chromedriver>=3.5.5",
    "selenium-stealth>=1.0.6",
    "requests>=2.31",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts", "."]
asyncio_mode = "auto"
```

- [ ] **Step 2: Install dependencies**

Run: `cd /home/tung491/Work/academic_wiki && uv pip install -e ".[mcp,dev]"`

- [ ] **Step 3: Create `academic_wiki_mcp/__init__.py`**

```python
from fastmcp import FastMCP

mcp = FastMCP("AcademicWikiServer")
```

- [ ] **Step 4: Create `academic_wiki_mcp/config.py`**

```python
import os
from pathlib import Path

WIKI_ROOT = Path(os.environ.get("WIKI_ROOT", "~/ObsidianVault/03-Resources")).expanduser()
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
BROWSER_TIMEOUT = int(os.environ.get("BROWSER_TIMEOUT", "15000"))
```

- [ ] **Step 5: Create `academic_wiki_mcp/models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Metadata:
    title: str
    authors: list[str]
    abstract: str
    doi: str
    arxiv: str | None
    url: str
    date: str
    year: int | None
    venue: str
    keywords: list[str]


@dataclass
class ContentBlock:
    type: str
    text: str | None = None
    figure_id: str | None = None


@dataclass
class Section:
    heading: str
    content: list[ContentBlock] = field(default_factory=list)


@dataclass
class Figure:
    id: str
    url: str
    filename: str
    caption: str
    data: bytes | None = None
    failed: bool = False
```

- [ ] **Step 6: Create `academic_wiki_mcp/server.py`**

```python
from academic_wiki_mcp import mcp
from academic_wiki_mcp.tools import download, discovery  # noqa: F401


def main():
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Create empty `__init__.py` files**

Create `academic_wiki_mcp/tools/__init__.py`, `academic_wiki_mcp/publishers/__init__.py`, `tests/mcp/__init__.py` as empty files.

- [ ] **Step 8: Create `tests/mcp/conftest.py`**

```python
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
```

- [ ] **Step 9: Create `tests/mcp/test_models.py`**

```python
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
```

- [ ] **Step 10: Run tests to verify scaffolding**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/mcp/test_models.py -v`
Expected: 4 PASSED

- [ ] **Step 11: Commit**

```bash
git add academic_wiki_mcp/ tests/mcp/ pyproject.toml
git commit -m "feat(mcp): scaffold academic wiki MCP server with models and config"
```

---

### Task 2: Identifier Detection

**Files:**
- Create: `academic_wiki_mcp/identifier.py`
- Create: `tests/mcp/test_identifier.py`

- [ ] **Step 1: Write tests for identifier detection**

```python
import pytest
from academic_wiki_mcp.identifier import detect


@pytest.mark.parametrize("input_str,expected_type,expected_id", [
    ("10.1109/TPAMI.2021.1234567", "doi", "10.1109/TPAMI.2021.1234567"),
    ("10.48550/arXiv.1706.03762", "doi", "10.48550/arXiv.1706.03762"),
    ("1706.03762", "arxiv", "1706.03762"),
    ("2301.12345v2", "arxiv", "2301.12345v2"),
    ("cs-AI/0301001", "arxiv", "cs-AI/0301001"),
    ("arXiv:1706.03762", "arxiv", "1706.03762"),
    ("arxiv:2301.12345", "arxiv", "2301.12345"),
    ("doi:10.1109/TPAMI.2021.1234567", "doi", "10.1109/TPAMI.2021.1234567"),
    ("https://arxiv.org/abs/1706.03762", "arxiv", "1706.03762"),
    ("https://arxiv.org/html/2301.12345v1", "arxiv", "2301.12345v1"),
    ("https://arxiv.org/pdf/1706.03762", "arxiv", "1706.03762"),
    ("https://doi.org/10.1109/TPAMI.2021.1234567", "doi", "10.1109/TPAMI.2021.1234567"),
    ("transformer attention", "unknown", "transformer attention"),
    ("", "unknown", ""),
])
def test_detect(input_str, expected_type, expected_id):
    id_type, raw_id = detect(input_str)
    assert id_type == expected_type
    assert raw_id == expected_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/mcp/test_identifier.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `identifier.py`**

```python
from __future__ import annotations
import re

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[^\s]+$")
ARXIV_PATTERN = re.compile(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z][\w-]*/\d{7})$", re.IGNORECASE)
ARXIV_URL_PATTERN = re.compile(r"arxiv\.org/(?:abs|html|pdf)/(.+?)(?:/|$)")
DOI_URL_PATTERN = re.compile(r"doi\.org/(10\.\d{4,9}/[^\s]+)")


def detect(identifier: str) -> tuple[str, str]:
    s = identifier.strip()
    if not s:
        return ("unknown", s)

    for prefix in ("arXiv:", "arxiv:", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break

    m = ARXIV_URL_PATTERN.search(s)
    if m:
        return ("arxiv", m.group(1))

    m = DOI_URL_PATTERN.search(s)
    if m:
        return ("doi", m.group(1))

    if DOI_PATTERN.match(s):
        return ("doi", s)

    if ARXIV_PATTERN.match(s):
        return ("arxiv", s)

    return ("unknown", identifier.strip())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_identifier.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/identifier.py tests/mcp/test_identifier.py
git commit -m "feat(mcp): identifier detection — DOI, arXiv ID, URLs, prefixed forms"
```

---

### Task 3: Markdown Generator

**Files:**
- Create: `academic_wiki_mcp/markdown.py`
- Create: `tests/mcp/test_markdown.py`

- [ ] **Step 1: Write tests for markdown generation**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/mcp/test_markdown.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `markdown.py`**

Port of `academic_web_clipper/lib/markdown.js` `toMarkdown()`:

```python
from __future__ import annotations
from academic_wiki_mcp.models import Metadata, Section, Figure


def format_inline_author(authors: list[str]) -> str:
    if not authors:
        return ""
    last_name = authors[0].strip().split()[-1]
    if len(authors) > 1:
        return f"{last_name} et al."
    return last_name


def sanitize_filename(name: str) -> str:
    import re
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name)
    cleaned = re.sub(r'\s+', '_', cleaned)
    return cleaned[:100]


def to_markdown(
    metadata: Metadata,
    sections: list[Section],
    figures: list[Figure],
    paper_id: str,
) -> str:
    fig_map = {f.id: f for f in figures}
    lines: list[str] = []

    lines.append("---")
    lines.append(f'title: "{metadata.title}"')
    if metadata.authors:
        author_list = ", ".join(metadata.authors)
        lines.append(f"authors: [{author_list}]")
        inline = format_inline_author(metadata.authors)
        lines.append(f'inline_author: "{inline}"')
    lines.append(f'paper-id: "{paper_id}"')

    has_ids = metadata.doi or metadata.arxiv or metadata.url
    if has_ids:
        lines.append("identifiers:")
        if metadata.doi:
            lines.append(f'  doi: "{metadata.doi}"')
        if metadata.arxiv:
            lines.append(f'  arxiv: "{metadata.arxiv}"')
        if metadata.url:
            lines.append(f'  url: "{metadata.url}"')

    if metadata.date:
        lines.append(f"date: {metadata.date}")
    if metadata.year is not None:
        lines.append(f"year: {metadata.year}")
    if metadata.venue:
        lines.append(f'venue: "{metadata.venue}"')
    if metadata.keywords:
        kw_list = ", ".join(metadata.keywords)
        lines.append(f"keywords: [{kw_list}]")
    lines.append("---")
    lines.append("")

    for section in sections:
        lines.append(f"## {section.heading}")
        for block in section.content:
            if block.type == "paragraph" and block.text:
                lines.append(block.text)
                lines.append("")
            elif block.type == "figure" and block.figure_id:
                fig = fig_map.get(block.figure_id)
                if fig:
                    if fig.failed:
                        lines.append("![[fig_missing.png]]")
                        lines.append(f"<!-- Image download failed for: {fig.filename} -->")
                    else:
                        lines.append(f"![[{fig.filename}]]")
                    if fig.caption:
                        lines.append(f"*{fig.caption}*")
                    lines.append("")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_markdown.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/markdown.py tests/mcp/test_markdown.py
git commit -m "feat(mcp): markdown generator — port of web clipper's toMarkdown"
```

---

### Task 4: Browser Abstraction Layer

**Files:**
- Create: `academic_wiki_mcp/browser.py`
- Create: `tests/mcp/test_browser.py`

- [ ] **Step 1: Write tests for the browser abstraction**

```python
import pytest
from academic_wiki_mcp.browser import (
    Element, BrowserBackend, PlaywrightBackend, SeleniumBackend,
    get_backend, detect_blocked,
)


def test_element_is_abstract():
    with pytest.raises(TypeError):
        Element()


def test_browser_backend_is_abstract():
    with pytest.raises(TypeError):
        BrowserBackend()


def test_get_backend_playwright():
    backend = get_backend("playwright")
    assert isinstance(backend, PlaywrightBackend)


def test_get_backend_selenium():
    backend = get_backend("selenium")
    assert isinstance(backend, SeleniumBackend)


def test_get_backend_invalid():
    with pytest.raises(ValueError, match="Unknown backend"):
        get_backend("firefox")


def test_detect_blocked_short_body():
    assert detect_blocked("<html><body>short</body></html>") is True


def test_detect_blocked_captcha():
    html = '<div id="cf-challenge-running">Checking your browser</div>' + "x" * 2000
    assert detect_blocked(html) is True


def test_detect_blocked_normal():
    html = "<html><body>" + "Normal content. " * 200 + "</body></html>"
    assert detect_blocked(html) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/mcp/test_browser.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `browser.py`**

```python
from __future__ import annotations
import asyncio
import re
from abc import ABC, abstractmethod
from typing import Any


class Element(ABC):
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
    @abstractmethod
    async def navigate(self, url: str) -> None: ...
    @abstractmethod
    async def wait_for_selector(self, selector: str, timeout: int = 15000) -> None: ...
    @abstractmethod
    async def query_selector(self, selector: str) -> Element | None: ...
    @abstractmethod
    async def query_selector_all(self, selector: str) -> list[Element]: ...
    @abstractmethod
    async def evaluate(self, js: str, *args: Any) -> Any: ...
    @abstractmethod
    async def download_image(self, url: str) -> bytes: ...
    @abstractmethod
    async def get_page_content(self) -> str: ...
    @abstractmethod
    async def sleep(self, ms: int) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...


_CAPTCHA_PATTERNS = [
    re.compile(r'id="cf-challenge', re.IGNORECASE),
    re.compile(r'class="g-recaptcha"', re.IGNORECASE),
    re.compile(r'<iframe[^>]*recaptcha', re.IGNORECASE),
]


def detect_blocked(html: str) -> bool:
    if len(html) < 1024:
        return True
    for pat in _CAPTCHA_PATTERNS:
        if pat.search(html):
            return True
    return False


# --- Playwright Backend ---

class PlaywrightElement(Element):
    def __init__(self, handle):
        self._h = handle

    async def text(self) -> str:
        return (await self._h.text_content()) or ""

    async def attribute(self, name: str) -> str | None:
        return await self._h.get_attribute(name)

    async def scroll_into_view(self) -> None:
        await self._h.scroll_into_view_if_needed()

    async def click(self) -> None:
        await self._h.click()

    async def children(self) -> list[Element]:
        handles = await self._h.query_selector_all(":scope > *")
        return [PlaywrightElement(h) for h in handles]

    async def next_sibling(self) -> Element | None:
        sib = await self._h.evaluate_handle(
            "el => el.nextElementSibling"
        )
        if await sib.evaluate("el => el === null"):
            return None
        return PlaywrightElement(sib.as_element())

    async def parent(self) -> Element | None:
        p = await self._h.evaluate_handle("el => el.parentElement")
        if await p.evaluate("el => el === null"):
            return None
        return PlaywrightElement(p.as_element())

    async def tag_name(self) -> str:
        return (await self._h.evaluate("el => el.tagName")).upper()


class PlaywrightBackend(BrowserBackend):
    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None

    async def _ensure_browser(self):
        if self._page is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._page = await self._browser.new_page()

    async def navigate(self, url: str) -> None:
        await self._ensure_browser()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def wait_for_selector(self, selector: str, timeout: int = 15000) -> None:
        await self._page.wait_for_selector(selector, timeout=timeout)

    async def query_selector(self, selector: str) -> Element | None:
        h = await self._page.query_selector(selector)
        return PlaywrightElement(h) if h else None

    async def query_selector_all(self, selector: str) -> list[Element]:
        handles = await self._page.query_selector_all(selector)
        return [PlaywrightElement(h) for h in handles]

    async def evaluate(self, js: str, *args: Any) -> Any:
        return await self._page.evaluate(js, *args)

    async def download_image(self, url: str) -> bytes:
        resp = await self._page.context.request.get(url)
        return await resp.body()

    async def get_page_content(self) -> str:
        return await self._page.content()

    async def sleep(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000)

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._page = None
        self._browser = None
        self._pw = None


# --- Selenium Backend ---

class SeleniumElement(Element):
    def __init__(self, el, driver):
        self._el = el
        self._driver = driver

    async def text(self) -> str:
        return self._el.text

    async def attribute(self, name: str) -> str | None:
        return self._el.get_attribute(name)

    async def scroll_into_view(self) -> None:
        self._driver.execute_script(
            "arguments[0].scrollIntoView({behavior:'instant',block:'center'})", self._el
        )

    async def click(self) -> None:
        self._el.click()

    async def children(self) -> list[Element]:
        kids = self._el.find_elements("css selector", ":scope > *")
        return [SeleniumElement(k, self._driver) for k in kids]

    async def next_sibling(self) -> Element | None:
        sib = self._driver.execute_script(
            "return arguments[0].nextElementSibling", self._el
        )
        return SeleniumElement(sib, self._driver) if sib else None

    async def parent(self) -> Element | None:
        p = self._driver.execute_script(
            "return arguments[0].parentElement", self._el
        )
        return SeleniumElement(p, self._driver) if p else None

    async def tag_name(self) -> str:
        return self._el.tag_name.upper()


class SeleniumBackend(BrowserBackend):
    def __init__(self):
        self._driver = None

    def _ensure_driver(self):
        if self._driver is None:
            import undetected_chromedriver as uc
            from selenium_stealth import stealth
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            self._driver = uc.Chrome(options=options)
            stealth(self._driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True)

    async def navigate(self, url: str) -> None:
        self._ensure_driver()
        self._driver.get(url)

    async def wait_for_selector(self, selector: str, timeout: int = 15000) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        WebDriverWait(self._driver, timeout / 1000).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

    async def query_selector(self, selector: str) -> Element | None:
        from selenium.webdriver.common.by import By
        els = self._driver.find_elements(By.CSS_SELECTOR, selector)
        return SeleniumElement(els[0], self._driver) if els else None

    async def query_selector_all(self, selector: str) -> list[Element]:
        from selenium.webdriver.common.by import By
        els = self._driver.find_elements(By.CSS_SELECTOR, selector)
        return [SeleniumElement(e, self._driver) for e in els]

    async def evaluate(self, js: str, *args: Any) -> Any:
        return self._driver.execute_script(js, *args)

    async def download_image(self, url: str) -> bytes:
        import requests
        cookies = {c["name"]: c["value"] for c in self._driver.get_cookies()}
        resp = requests.get(url, cookies=cookies, timeout=30)
        resp.raise_for_status()
        return resp.content

    async def get_page_content(self) -> str:
        return self._driver.page_source

    async def sleep(self, ms: int) -> None:
        await asyncio.sleep(ms / 1000)

    async def close(self) -> None:
        if self._driver:
            self._driver.quit()
            self._driver = None


_backend_override: dict[str, str] = {}


def get_backend(name: str) -> BrowserBackend:
    if name == "playwright":
        return PlaywrightBackend()
    elif name == "selenium":
        return SeleniumBackend()
    raise ValueError(f"Unknown backend: {name}")


def get_backend_for_publisher(publisher_domain: str, default: str = "playwright", fallback: str = "selenium") -> tuple[BrowserBackend, str]:
    """Returns (backend, backend_name). Uses session-learned overrides if a previous fallback succeeded."""
    name = _backend_override.get(publisher_domain, default)
    return get_backend(name), name


def record_backend_success(publisher_domain: str, backend_name: str) -> None:
    """Record that a backend worked for a publisher, so future calls skip the failing one."""
    _backend_override[publisher_domain] = backend_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_browser.py -v`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/browser.py tests/mcp/test_browser.py
git commit -m "feat(mcp): browser abstraction — Playwright + stealth Selenium backends"
```

---

### Task 5: Publisher Base Class and Routing

**Files:**
- Create: `academic_wiki_mcp/publishers/base.py`
- Modify: `academic_wiki_mcp/publishers/__init__.py`
- Create: `tests/mcp/test_publisher_base.py`

- [ ] **Step 1: Write tests**

```python
import pytest
from academic_wiki_mcp.publishers import find_publisher
from academic_wiki_mcp.publishers.base import BasePublisher


def test_find_publisher_exact():
    pub = find_publisher("https://arxiv.org/html/1706.03762")
    assert pub is not None
    assert type(pub).__name__ == "ArxivPublisher"


def test_find_publisher_www_prefix():
    pub = find_publisher("https://www.sciencedirect.com/science/article/pii/S0001")
    assert pub is not None
    assert type(pub).__name__ == "ScienceDirectPublisher"


def test_find_publisher_unknown():
    assert find_publisher("https://example.com/paper") is None


def test_find_publisher_ieee():
    pub = find_publisher("https://ieeexplore.ieee.org/document/123456")
    assert type(pub).__name__ == "IEEEPublisher"


def test_find_publisher_mdpi_www():
    pub = find_publisher("https://www.mdpi.com/1234-5678/1/1/1")
    assert type(pub).__name__ == "MDPIPublisher"


def test_base_publisher_is_abstract():
    with pytest.raises(TypeError):
        BasePublisher()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/mcp/test_publisher_base.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `publishers/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod

from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, Figure


class BasePublisher(ABC):
    backend: str = "playwright"
    fallback_backend: str = "selenium"

    @abstractmethod
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata: ...

    @abstractmethod
    async def extract_sections(self, browser: BrowserBackend) -> list[Section]: ...

    @abstractmethod
    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]: ...

    async def _meta_tag(self, browser: BrowserBackend, name: str) -> str:
        el = await browser.query_selector(f'meta[name="{name}"]')
        if el:
            return (await el.attribute("content")) or ""
        return ""

    async def _meta_tags(self, browser: BrowserBackend, name: str) -> list[str]:
        els = await browser.query_selector_all(f'meta[name="{name}"]')
        results = []
        for el in els:
            val = await el.attribute("content")
            if val:
                results.append(val.strip())
        return results

    async def _fallback_metadata(self, browser: BrowserBackend) -> Metadata:
        return Metadata(
            title=await self._meta_tag(browser, "citation_title"),
            authors=await self._meta_tags(browser, "citation_author"),
            abstract="",
            doi=await self._meta_tag(browser, "citation_doi"),
            arxiv=None,
            url="",
            date=await self._meta_tag(browser, "citation_publication_date"),
            year=None,
            venue=await self._meta_tag(browser, "citation_journal_title"),
            keywords=[],
        )
```

- [ ] **Step 4: Implement `publishers/__init__.py` with routing**

```python
from __future__ import annotations
from urllib.parse import urlparse

from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.publishers.arxiv import ArxivPublisher
from academic_wiki_mcp.publishers.ieee import IEEEPublisher
from academic_wiki_mcp.publishers.springer import SpringerPublisher
from academic_wiki_mcp.publishers.sciencedirect import ScienceDirectPublisher
from academic_wiki_mcp.publishers.mdpi import MDPIPublisher
from academic_wiki_mcp.publishers.wiley import WileyPublisher
from academic_wiki_mcp.publishers.tandfonline import TandFPublisher
from academic_wiki_mcp.publishers.asce import ASCEPublisher

PUBLISHERS: list[tuple[str, type[BasePublisher]]] = [
    ("arxiv.org", ArxivPublisher),
    ("ieeexplore.ieee.org", IEEEPublisher),
    ("link.springer.com", SpringerPublisher),
    ("sciencedirect.com", ScienceDirectPublisher),
    ("mdpi.com", MDPIPublisher),
    ("onlinelibrary.wiley.com", WileyPublisher),
    ("tandfonline.com", TandFPublisher),
    ("ascelibrary.org", ASCEPublisher),
]


def find_publisher(url: str) -> BasePublisher | None:
    hostname = urlparse(url).hostname or ""
    for suffix, cls in PUBLISHERS:
        if hostname == suffix or hostname.endswith("." + suffix):
            return cls()
    return None
```

- [ ] **Step 5: Create stub publisher files**

Create minimal stubs for all 8 publishers so the imports in `__init__.py` resolve. Each stub:

```python
# academic_wiki_mcp/publishers/arxiv.py (and similarly for all 8)
from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, Figure


class ArxivPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        raise NotImplementedError

    async def extract_sections(self, browser: BrowserBackend) -> list[Section]:
        raise NotImplementedError

    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]:
        raise NotImplementedError
```

Repeat for `IEEEPublisher`, `SpringerPublisher`, `ScienceDirectPublisher`, `MDPIPublisher`, `WileyPublisher`, `TandFPublisher`, `ASCEPublisher`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_publisher_base.py -v`
Expected: All PASSED

- [ ] **Step 7: Commit**

```bash
git add academic_wiki_mcp/publishers/
git add tests/mcp/test_publisher_base.py
git commit -m "feat(mcp): publisher base class, routing, and 8 stub extractors"
```

---

### Task 6: arXiv Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/arxiv.py`
- Create: `tests/mcp/fixtures/arxiv_sample.html`
- Create: `tests/mcp/test_arxiv.py`

Reference: `academic_web_clipper/content/arxiv.js`

- [ ] **Step 1: Create a minimal HTML fixture**

Save a minimal arXiv HTML page at `tests/mcp/fixtures/arxiv_sample.html` that contains the LaTeXML structure: `h1.ltx_title` (with `.ltx_tag_document` child), `.ltx_authors .ltx_personname`, `.ltx_abstract .ltx_p`, `.ltx_section` with `.ltx_para .ltx_p`, `.ltx_figure img`, `.ltx_bibliography .ltx_bibitem`.

- [ ] **Step 2: Write tests using MockBrowser**

Add to `tests/mcp/conftest.py` a `MockBrowser` class that loads an HTML fixture and resolves selectors using `BeautifulSoup` (or similar). Alternatively, test the publisher by mocking `BrowserBackend` methods to return canned results.

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from academic_wiki_mcp.publishers.arxiv import ArxivPublisher


@pytest.fixture
def arxiv_publisher():
    return ArxivPublisher()


@pytest.mark.asyncio
async def test_arxiv_extract_metadata(arxiv_publisher):
    browser = AsyncMock()
    # Mock title element (with clone+strip behavior)
    title_el = AsyncMock()
    title_el.text.return_value = "Attention Is All You Need"
    browser.query_selector.side_effect = lambda sel: {
        "h1.ltx_title": title_el,
        'meta[name="citation_doi"]': _mock_meta("10.48550/arXiv.1706.03762"),
        'meta[name="citation_date"]': _mock_meta("2017-06-12"),
        'meta[name="citation_journal_title"]': _mock_meta("arXiv"),
    }.get(sel)
    browser.query_selector_all.side_effect = lambda sel: {
        ".ltx_authors .ltx_personname": [_mock_text("Ashish Vaswani"), _mock_text("Noam Shazeer")],
        ".ltx_abstract .ltx_p": [_mock_text("We propose the Transformer.")],
        ".ltx_classification .ltx_text": [_mock_text("cs.CL")],
    }.get(sel, [])

    meta = await arxiv_publisher.extract_metadata(browser)
    assert meta.title == "Attention Is All You Need"
    assert len(meta.authors) == 2
    assert meta.doi == "10.48550/arXiv.1706.03762"


def _mock_meta(content):
    el = AsyncMock()
    el.attribute.return_value = content
    return el


def _mock_text(txt):
    el = AsyncMock()
    el.text.return_value = txt
    return el
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/mcp/test_arxiv.py -v`
Expected: FAIL — `NotImplementedError`

- [ ] **Step 4: Implement `arxiv.py`**

Port CSS selectors and logic from `academic_web_clipper/content/arxiv.js`:

```python
from __future__ import annotations
import re
from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.browser import BrowserBackend, Element
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class ArxivPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        title = ""
        title_el = await browser.query_selector("h1.ltx_title")
        if title_el:
            title = await browser.evaluate("""
                () => {
                    const el = document.querySelector('h1.ltx_title');
                    if (!el) return '';
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('.ltx_tag_document').forEach(t => t.remove());
                    return clone.textContent.replace(/^Title:\\s*/i, '').trim();
                }
            """)
        if not title:
            title = await self._meta_tag(browser, "citation_title")

        authors_els = await browser.query_selector_all(".ltx_authors .ltx_personname")
        authors = [await el.text() for el in authors_els]
        if not authors:
            authors = await self._meta_tags(browser, "citation_author")

        abstract_els = await browser.query_selector_all(".ltx_abstract .ltx_p")
        abstract = " ".join([await el.text() for el in abstract_els])

        doi = await self._meta_tag(browser, "citation_doi")
        date = await self._meta_tag(browser, "citation_date")
        if not date:
            date = await self._meta_tag(browser, "citation_publication_date")
        venue = await self._meta_tag(browser, "citation_journal_title") or "arXiv"

        keywords_els = await browser.query_selector_all(".ltx_classification .ltx_text")
        keywords = [await el.text() for el in keywords_els]

        year = None
        if date:
            m = re.search(r"(\d{4})", date)
            if m:
                year = int(m.group(1))

        return Metadata(
            title=title, authors=authors, abstract=abstract,
            doi=doi, arxiv=None, url="", date=date, year=year,
            venue=venue, keywords=keywords,
        )

    async def extract_sections(self, browser: BrowserBackend) -> list[Section]:
        sections: list[Section] = []

        abstract_els = await browser.query_selector_all(".ltx_abstract .ltx_p")
        if abstract_els:
            content = [ContentBlock(type="paragraph", text=await el.text()) for el in abstract_els]
            sections.append(Section(heading="Abstract", content=content))

        section_els = await browser.query_selector_all(".ltx_section")
        for sec_el in section_els:
            heading_el = await sec_el.children()
            heading = ""
            for child in heading_el:
                tag = await child.tag_name()
                if tag in ("H2", "H3", "H4", "H5", "H6"):
                    heading = await child.text()
                    break
            if not heading:
                cls = await sec_el.attribute("class") or ""
                heading = cls

            paras = await browser.evaluate("""
                (secEl) => {
                    const ps = secEl.querySelectorAll('.ltx_para .ltx_p');
                    return Array.from(ps).map(p => p.textContent.trim());
                }
            """, sec_el)

            content: list[ContentBlock] = []
            for p_text in (paras or []):
                if p_text:
                    content.append(ContentBlock(type="paragraph", text=p_text))

            fig_imgs = await browser.evaluate("""
                (secEl) => {
                    const imgs = secEl.querySelectorAll('.ltx_figure img');
                    return Array.from(imgs).map(img =>
                        new URL(img.src || img.getAttribute('src'), document.baseURI).href
                    );
                }
            """, sec_el)
            for url in (fig_imgs or []):
                content.append(ContentBlock(type="figure", figure_id=url))

            sections.append(Section(heading=heading, content=content))

        ref_els = await browser.query_selector_all(".ltx_bibliography .ltx_bibitem")
        if ref_els:
            content = []
            for i, el in enumerate(ref_els, 1):
                txt = await el.text()
                content.append(ContentBlock(type="paragraph", text=f"{i}. {txt}"))
            sections.append(Section(heading="References", content=content))

        return sections

    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]:
        figures: list[Figure] = []
        seen: set[str] = set()
        fig_count = 0

        data = await browser.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('.ltx_figure').forEach(fig => {
                    const img = fig.querySelector('img');
                    if (!img) return;
                    const url = new URL(img.src || img.getAttribute('src'), document.baseURI).href;
                    const cap = fig.querySelector('figcaption.ltx_caption, .ltx_caption');
                    results.push({
                        url: url,
                        caption: cap ? cap.textContent.trim() : '',
                    });
                });
                return results;
            }
        """)

        for item in (data or []):
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            fig_count += 1
            figures.append(Figure(
                id=url,
                url=url,
                filename=f"fig{fig_count}.png",
                caption=item["caption"],
            ))

        return figures
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/mcp/test_arxiv.py -v`
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add academic_wiki_mcp/publishers/arxiv.py tests/mcp/test_arxiv.py tests/mcp/fixtures/
git commit -m "feat(mcp): arXiv publisher extractor — port from web clipper"
```

---

### Task 7: IEEE Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/ieee.py`
- Create: `tests/mcp/test_ieee.py`

Reference: `academic_web_clipper/content/ieee.js`

- [ ] **Step 1: Write tests using mocked browser**

Test metadata extraction with IEEE-specific selectors: `.document-title`, `.authors-info .author-name`, `.abstract-text .u-mb-1`, date stripping "Date of Publication:" prefix, `img[src*="mediastore"]` for figures, `-small` → `-large` URL transform.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/mcp/test_ieee.py -v`

- [ ] **Step 3: Implement `ieee.py`**

Port from `academic_web_clipper/content/ieee.js`. Key patterns:
- Title: `.document-title` → fallback `meta[property="og:title"]`
- Authors: `.authors-info .author-name` → `.authors-info span[id^="author"]`
- Date: strip `"Date of Publication:"` prefix, parse to ISO
- Figures: `img[src*="mediastore"]`, skip `icon`/`logo`, replace `-small.`→`-large.` and `-small-`→`-large-`
- Lazy scroll: 300ms per image
- Caption: `.figcaption, figcaption, .caption, .fig-caption`, validate `/^fig/i` or len < 200

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(mcp): IEEE publisher extractor"
```

---

### Task 8: Springer Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/springer.py`
- Create: `tests/mcp/test_springer.py`

Reference: `academic_web_clipper/content/springer.js`

- [ ] **Step 1: Write tests**

Key patterns: `h1.c-article-title`, `[data-test="author-name"]`, `#Abs1-content p`, `.c-article-section` (skip `Abs1`), `.c-article-section__figure` (avoid sidebar dupes), `data-src` attribute, 300ms scroll, `normalizeUrl`.

- [ ] **Step 2-5: Red-green-commit cycle**

---

### Task 9: ScienceDirect Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/sciencedirect.py`
- Create: `tests/mcp/test_sciencedirect.py`

Reference: `academic_web_clipper/content/sciencedirect.js`

- [ ] **Step 1: Write tests**

Key patterns: `h1.title-text span.title-text`, `.author span.text`, `[id*="abspara"]`, TreeWalker on `#body` (implemented via `evaluate(js)` running the walker in-page), `data-src` attribute, skip `clear.gif|1x1|blank`, 500ms scroll delay.

- [ ] **Step 2-5: Red-green-commit cycle**

---

### Task 10: MDPI Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/mdpi.py`
- Create: `tests/mcp/test_mdpi.py`

Reference: `academic_web_clipper/content/mdpi.js`

- [ ] **Step 1: Write tests**

Key patterns: `h1.title`, `.art-authors .sciprofiles-link`, `.art-abstract p`, filtered TreeWalker on `.html-body`, `.html-h2`/`.html-h4` headings, `a.html-img-zoom img` → fallback `.html-figpopup img`, `.html-table_show` table extraction, keyword semicolon stripping, 200ms scroll.

- [ ] **Step 2-5: Red-green-commit cycle**

---

### Task 11: Wiley Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/wiley.py`
- Create: `tests/mcp/test_wiley.py`

Reference: `academic_web_clipper/content/wiley.js`

- [ ] **Step 1: Write tests**

Key patterns: `.citation__title`, `.loa-authors-trunc .author-name span`, 3-tier abstract selectors, `.article-section__content`, `figure.figure img.figure__image` (must contain `cms/asset`), table extraction, `seenAbstract` skip logic, 300ms scroll.

- [ ] **Step 2-5: Red-green-commit cycle**

---

### Task 12: Taylor & Francis Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/tandfonline.py`
- Create: `tests/mcp/test_tandfonline.py`

Reference: `academic_web_clipper/content/tandfonline.js`

- [ ] **Step 1: Write tests**

The most complex extractor. Key patterns:
- Popup table extraction: `extractPopupTables` — click `.tableView a` matching `/display\s*table/i`, poll 300ms×20 for new `table`, close modal via `button.modal-close` → `button.ref-close` → Escape key
- Section extraction on `.hlFld-Fulltext` or `.article__body` via `querySelectorAll` in document order
- `img[src*="cms/asset"]` figure filter
- Caption: `.caption, figcaption, .NLM_caption` + sibling fallback

- [ ] **Step 2-5: Red-green-commit cycle**

---

### Task 13: ASCE Publisher Extractor

**Files:**
- Modify: `academic_wiki_mcp/publishers/asce.py`
- Create: `tests/mcp/test_asce.py`

Reference: `academic_web_clipper/content/asce.js`

- [ ] **Step 1: Write tests**

Key patterns: `h1.citation__title`, abstract by iterating `section` elements for h2 matching `/^abstract$/i`, `div.core-container section` with `sec.children` walk, `figure img` with `data-src`, skip `/icon|logo|spinner/i`, table extraction, 300ms scroll, no references section.

- [ ] **Step 2-5: Red-green-commit cycle**

---

### Task 14: Semantic Scholar Discovery Tools

**Files:**
- Create: `academic_wiki_mcp/tools/discovery.py`
- Create: `tests/mcp/test_discovery.py`

- [ ] **Step 1: Write tests**

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from academic_wiki_mcp.tools.discovery import (
    _s2_get, _search, _references, _citations, _recommendations,
)


@pytest.mark.asyncio
async def test_search_returns_results():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [
        {"paperId": "abc", "title": "Test", "authors": [{"name": "A"}],
         "year": 2024, "venue": "V", "abstract": "Ab", "externalIds": {"DOI": "10.1/x"}},
    ]}
    with patch("requests.get", return_value=mock_resp):
        results = await _search("transformer", limit=1)
        assert len(results) == 1
        assert results[0]["title"] == "Test"


@pytest.mark.asyncio
async def test_recommendations_404_returns_empty():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.get", return_value=mock_resp):
        results = await _recommendations("abc123")
        assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement `discovery.py`**

```python
from __future__ import annotations
import time
import requests
from academic_wiki_mcp import mcp
from academic_wiki_mcp.config import SEMANTIC_SCHOLAR_API_KEY
from academic_wiki_mcp.identifier import detect

S2_GRAPH = "https://api.semanticscholar.org/graph/v1"
S2_RECS = "https://api.semanticscholar.org/recommendations/v1"
S2_FIELDS = "paperId,title,authors,year,venue,abstract,externalIds,citationCount"


def _headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        h["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    return h


def _s2_get(url: str, params: dict | None = None, max_retries: int = 5) -> requests.Response | None:
    for attempt in range(max_retries):
        resp = requests.get(url, params=params, headers=_headers(), timeout=30)
        if resp.status_code == 200:
            return resp
        if resp.status_code == 404:
            return resp
        if resp.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
    return None


def _normalize_s2_paper(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    return {
        "paperId": p.get("paperId", ""),
        "title": p.get("title", ""),
        "authors": [a["name"] for a in (p.get("authors") or [])],
        "year": p.get("year"),
        "venue": p.get("venue", ""),
        "abstract": p.get("abstract", ""),
        "doi": ext.get("DOI", ""),
        "arxiv": ext.get("ArXiv", ""),
        "citationCount": p.get("citationCount", 0),
    }


async def _search(query: str, venue: str | None = None, year: str | None = None, limit: int = 10) -> list[dict]:
    params: dict[str, str] = {"query": query, "limit": str(limit), "fields": S2_FIELDS}
    if venue:
        params["venue"] = venue
    if year:
        params["year"] = year
    resp = _s2_get(f"{S2_GRAPH}/paper/search", params=params)
    if not resp or resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("data") or [])]


async def _references(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(f"{S2_GRAPH}/paper/{paper_id}/references", params={"fields": S2_FIELDS, "limit": str(limit)})
    if not resp or resp.status_code != 200:
        return []
    return [_normalize_s2_paper(r["citedPaper"]) for r in (resp.json().get("data") or []) if r.get("citedPaper")]


async def _citations(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(f"{S2_GRAPH}/paper/{paper_id}/citations", params={"fields": S2_FIELDS, "limit": str(limit)})
    if not resp or resp.status_code != 200:
        return []
    return [_normalize_s2_paper(r["citingPaper"]) for r in (resp.json().get("data") or []) if r.get("citingPaper")]


async def _recommendations(paper_id: str, limit: int = 20) -> list[dict]:
    resp = _s2_get(f"{S2_RECS}/papers/forpaper/{paper_id}", params={"fields": S2_FIELDS, "limit": str(limit)})
    if not resp or resp.status_code == 404:
        return []
    if resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("recommendedPapers") or [])]


def _resolve_s2_id(identifier: str) -> str:
    id_type, raw = detect(identifier)
    if id_type == "doi":
        return f"DOI:{raw}"
    if id_type == "arxiv":
        return f"ARXIV:{raw}"
    return identifier


@mcp.tool()
async def semantic_scholar_search(
    query: str,
    venue: str | None = None,
    year: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Semantic Scholar for papers by keyword query."""
    return await _search(query, venue=venue, year=year, limit=limit)


@mcp.tool()
async def discover_related(identifier: str, limit: int = 10) -> dict:
    """Discover related papers via Semantic Scholar citation graph and recommendations."""
    s2_id = _resolve_s2_id(identifier)

    refs = await _references(s2_id, limit=50)
    cites = await _citations(s2_id, limit=50)
    recs = await _recommendations(s2_id, limit=20)

    seen: set[str] = set()
    combined: list[dict] = []
    for paper in refs + cites + recs:
        pid = paper["paperId"]
        if pid and pid not in seen:
            seen.add(pid)
            combined.append(paper)

    combined.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    return {"related": combined[:limit], "total_found": len(combined)}
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/tools/discovery.py tests/mcp/test_discovery.py
git commit -m "feat(mcp): Semantic Scholar search and discover_related tools"
```

---

### Task 15: Download Paper Tool (Integration)

**Files:**
- Create: `academic_wiki_mcp/tools/download.py`
- Create: `tests/mcp/test_download.py`

- [ ] **Step 1: Write tests**

Test the full pipeline with mocked browser and mocked `paper_id.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from academic_wiki_mcp.tools.download import _download_paper_impl
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


@pytest.mark.asyncio
async def test_download_creates_output_dir(tmp_wiki, sample_metadata):
    publisher = AsyncMock()
    publisher.extract_metadata.return_value = sample_metadata
    publisher.extract_sections.return_value = [
        Section(heading="Abstract", content=[
            ContentBlock(type="paragraph", text="Test"),
        ]),
    ]
    publisher.extract_figures.return_value = []

    browser = AsyncMock()
    browser.get_page_content.return_value = "<html>" + "x" * 2000 + "</html>"

    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent), \
         patch("academic_wiki_mcp.tools.download.find_publisher", return_value=publisher), \
         patch("academic_wiki_mcp.tools.download.get_backend_for_publisher", return_value=(browser, "playwright")), \
         patch("academic_wiki_mcp.tools.download._resolve_url", return_value="https://arxiv.org/html/1706.03762"):
        result = await _download_paper_impl("1706.03762", str(tmp_wiki))

    assert result["is_new"] is True
    paper_dir = tmp_wiki / "raw" / "papers" / result["paper_id"]
    assert paper_dir.exists()
    assert (paper_dir / f"{result['paper_id']}.md").exists()


@pytest.mark.asyncio
async def test_download_dedup_returns_existing(tmp_wiki, sample_metadata):
    (tmp_wiki / "wiki/papers/vaswani-2017-attention.md").write_text(
        "---\npaper-id: vaswani-2017-attention\nidentifiers:\n  doi: \"10.48550/arXiv.1706.03762\"\n---\n"
    )

    publisher = AsyncMock()
    publisher.extract_metadata.return_value = sample_metadata
    publisher.extract_sections.return_value = []
    publisher.extract_figures.return_value = []

    browser = AsyncMock()
    browser.get_page_content.return_value = "<html>" + "x" * 2000 + "</html>"

    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent), \
         patch("academic_wiki_mcp.tools.download.find_publisher", return_value=publisher), \
         patch("academic_wiki_mcp.tools.download.get_backend_for_publisher", return_value=(browser, "playwright")), \
         patch("academic_wiki_mcp.tools.download._resolve_url", return_value="https://arxiv.org/html/1706.03762"):
        result = await _download_paper_impl("10.48550/arXiv.1706.03762", str(tmp_wiki))

    assert result["is_new"] is False
    assert result["paper_id"] == "vaswani-2017-attention"
```

- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement `download.py`**

```python
from __future__ import annotations
import re
import sys
from pathlib import Path

import requests

from academic_wiki_mcp import mcp
from academic_wiki_mcp.browser import get_backend, get_backend_for_publisher, record_backend_success, detect_blocked, BrowserBackend
from academic_wiki_mcp.config import WIKI_ROOT
from academic_wiki_mcp.identifier import detect
from academic_wiki_mcp.markdown import to_markdown
from academic_wiki_mcp.models import Metadata, Figure
from academic_wiki_mcp.publishers import find_publisher

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from academic_wiki_lib.paper_id import (
    generate_paper_id,
    find_existing_paper_by_identifiers,
    resolve_collision,
)


def _resolve_url(id_type: str, raw_id: str) -> str:
    if id_type == "arxiv":
        return f"https://arxiv.org/html/{raw_id}"
    if id_type == "doi":
        resp = requests.head(f"https://doi.org/{raw_id}", allow_redirects=True, timeout=15)
        return resp.url
    raise ValueError(f"Cannot resolve identifier: {raw_id}")


async def _download_paper_impl(identifier: str, wiki_path: str) -> dict:
    wp = Path(wiki_path).resolve()
    wiki_root = WIKI_ROOT.resolve()
    if not wp.exists() or not wp.is_relative_to(wiki_root):
        return {"error": f"Invalid wiki_path: {wiki_path}"}

    id_type, raw_id = detect(identifier)
    if id_type == "unknown":
        return {"error": f"Cannot detect identifier type for: {identifier}. Use semantic_scholar_search first."}

    url = _resolve_url(id_type, raw_id)
    publisher = find_publisher(url)
    is_arxiv_abs_fallback = False

    if not publisher and id_type == "arxiv":
        url = f"https://arxiv.org/abs/{raw_id}"
        publisher = find_publisher(url)
        is_arxiv_abs_fallback = True

    if not publisher:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname
        return {"error": f"Publisher not supported: {domain}"}

    from urllib.parse import urlparse as _urlparse
    pub_domain = _urlparse(url).hostname or ""
    browser, backend_name = get_backend_for_publisher(pub_domain, publisher.backend, publisher.fallback_backend)
    try:
        await browser.navigate(url)
        html = await browser.get_page_content()

        if detect_blocked(html):
            await browser.close()
            fallback_name = publisher.fallback_backend if backend_name == publisher.backend else publisher.backend
            browser = get_backend(fallback_name)
            await browser.navigate(url)
            html = await browser.get_page_content()
            if detect_blocked(html):
                return {"error": f"Both backends blocked for {url}"}
            backend_name = fallback_name

        record_backend_success(pub_domain, backend_name)

        metadata = await publisher.extract_metadata(browser)
        sections = await publisher.extract_sections(browser)
        figures = await publisher.extract_figures(browser)

        # Download figures while browser is still open (for auth cookies)
        for fig in figures:
            if fig.url and not fig.failed:
                try:
                    fig.data = await browser.download_image(fig.url)
                except Exception:
                    fig.failed = True
    finally:
        await browser.close()

    if id_type == "arxiv":
        metadata.arxiv = raw_id
    metadata.url = url

    identifiers = {}
    if metadata.doi:
        identifiers["doi"] = metadata.doi
    if metadata.arxiv:
        identifiers["arxiv"] = metadata.arxiv
    if metadata.url:
        identifiers["url"] = metadata.url

    existing = find_existing_paper_by_identifiers(str(wp), identifiers)
    if existing:
        return {"paper_id": existing, "path": str(wp / "raw/papers" / existing),
                "title": metadata.title, "authors": metadata.authors, "is_new": False}

    last_name = metadata.authors[0].split()[-1] if metadata.authors else "unknown"
    year = metadata.year or 0
    paper_id = generate_paper_id(last_name, year, metadata.title)
    paper_id = resolve_collision(str(wp), paper_id)

    paper_dir = wp / "raw" / "papers" / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
        if fig.data and not fig.failed:
            (paper_dir / fig.filename).write_bytes(fig.data)

    md = to_markdown(metadata, sections, figures, paper_id=paper_id)
    (paper_dir / f"{paper_id}.md").write_text(md, encoding="utf-8")

    result = {
        "paper_id": paper_id,
        "path": str(paper_dir),
        "title": metadata.title,
        "authors": metadata.authors,
        "is_new": True,
    }
    if is_arxiv_abs_fallback:
        result["partial"] = True
    return result


@mcp.tool()
async def download_paper(identifier: str, wiki_path: str) -> dict:
    """Download a paper by DOI or arXiv ID, extract content, save to wiki."""
    return await _download_paper_impl(identifier, wiki_path)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/mcp/test_download.py -v`

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/tools/download.py tests/mcp/test_download.py
git commit -m "feat(mcp): download_paper tool — full pipeline with dedup and fallback"
```

---

### Task 16: Server Entry Point and Smoke Test

**Files:**
- Modify: `academic_wiki_mcp/server.py`
- No new test file — manual smoke test

- [ ] **Step 1: Ensure `server.py` imports both tool modules**

Already done in Task 1. Verify:

```python
from academic_wiki_mcp import mcp
from academic_wiki_mcp.tools import download, discovery  # noqa: F401
```

- [ ] **Step 2: Install Playwright browsers**

Run: `playwright install chromium`

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/mcp/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Smoke test the server**

Run: `python -m academic_wiki_mcp.server stdio`
Expected: Server starts and accepts MCP tool calls via stdio. Ctrl+C to stop.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(mcp): academic wiki MCP server — all tools, all publishers, tests passing"
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | Scaffolding, models, config | test_models.py |
| 2 | Identifier detection | test_identifier.py |
| 3 | Markdown generator | test_markdown.py |
| 4 | Browser abstraction | test_browser.py |
| 5 | Publisher base + routing | test_publisher_base.py |
| 6 | arXiv extractor | test_arxiv.py |
| 7 | IEEE extractor | test_ieee.py |
| 8 | Springer extractor | test_springer.py |
| 9 | ScienceDirect extractor | test_sciencedirect.py |
| 10 | MDPI extractor | test_mdpi.py |
| 11 | Wiley extractor | test_wiley.py |
| 12 | T&F extractor | test_tandfonline.py |
| 13 | ASCE extractor | test_asce.py |
| 14 | Semantic Scholar tools | test_discovery.py |
| 15 | Download paper tool | test_download.py |
| 16 | Server entry point | Manual smoke test |
