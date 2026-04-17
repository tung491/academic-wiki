from __future__ import annotations

from academic_wiki_mcp.publishers.base import BasePublisher, _normalize_date
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class ArxivPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title: clone h1.ltx_title and remove .ltx_tag_document children
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

        # Authors
        authors_els = await browser.query_selector_all(".ltx_authors .ltx_personname")
        authors = [await el.text() for el in authors_els]
        if not authors:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract
        abstract_els = await browser.query_selector_all(".ltx_abstract .ltx_p")
        abstract = " ".join([await el.text() for el in abstract_els])

        doi = await self._meta_tag(browser, "citation_doi")

        date = await self._meta_tag(browser, "citation_date")
        if not date:
            date = await self._meta_tag(browser, "citation_publication_date")

        venue = await self._meta_tag(browser, "citation_journal_title") or "arXiv"

        keywords_els = await browser.query_selector_all(".ltx_classification .ltx_text")
        keywords = [await el.text() for el in keywords_els]

        date, year = _normalize_date(date)

        return Metadata(
            title=title,
            authors=authors,
            abstract=abstract,
            doi=doi,
            arxiv=None,
            url="",
            date=date,
            year=year,
            venue=venue,
            keywords=keywords,
        )

    async def extract_sections(self, browser: BrowserBackend) -> list[Section]:
        sections: list[Section] = []

        # Abstract as first section
        abstract_els = await browser.query_selector_all(".ltx_abstract .ltx_p")
        if abstract_els:
            content = [
                ContentBlock(type="paragraph", text=await el.text())
                for el in abstract_els
            ]
            sections.append(Section(heading="Abstract", content=content))

        # Body sections
        section_els = await browser.query_selector_all(".ltx_section")
        for sec_el in section_els:
            # Heading: first .ltx_title inside the section
            heading_el = await browser.evaluate("""
                (secEl) => {
                    const h = secEl.querySelector('.ltx_title');
                    return h ? h.textContent.trim() : 'Untitled Section';
                }
            """, sec_el)
            heading = heading_el or "Untitled Section"

            # Paragraphs
            paras = await browser.evaluate("""
                (secEl) => {
                    return Array.from(secEl.querySelectorAll('.ltx_para .ltx_p'))
                        .map(p => p.textContent.trim())
                        .filter(Boolean);
                }
            """, sec_el)

            content: list[ContentBlock] = []
            for p_text in (paras or []):
                if p_text:
                    content.append(ContentBlock(type="paragraph", text=p_text))

            # Figure references
            fig_imgs = await browser.evaluate("""
                (secEl) => {
                    return Array.from(secEl.querySelectorAll('.ltx_figure img'))
                        .map(img => img.src || img.getAttribute('src') || '')
                        .filter(Boolean);
                }
            """, sec_el)
            for fig_url in (fig_imgs or []):
                content.append(ContentBlock(type="figure", figure_id=fig_url))

            if content:
                sections.append(Section(heading=heading, content=content))

        # References
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

        data = await browser.evaluate("""
            () => {
                const seen = new Set();
                const results = [];
                document.querySelectorAll('.ltx_figure').forEach(fig => {
                    const img = fig.querySelector('img');
                    if (!img) return;
                    const src = img.src || img.getAttribute('src') || '';
                    if (!src || seen.has(src)) return;
                    seen.add(src);
                    const cap = fig.querySelector('figcaption.ltx_caption, .ltx_caption');
                    results.push({
                        url: src,
                        caption: cap ? cap.textContent.trim() : '',
                    });
                });
                return results;
            }
        """)

        for i, item in enumerate(data or [], 1):
            figures.append(Figure(
                id=item["url"],
                url=item["url"],
                filename=f"fig{i}.png",
                caption=item["caption"],
            ))

        return figures
