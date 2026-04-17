from __future__ import annotations

from academic_wiki_mcp.publishers.base import BasePublisher, _normalize_date
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class TandFPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title
        title_el = await browser.query_selector(".NLM_article-title")
        if title_el:
            title = await title_el.text()
        else:
            alt_el = await browser.query_selector(".article-title")
            if alt_el:
                title = await alt_el.text()
            else:
                h1_el = await browser.query_selector("h1")
                if h1_el:
                    title = await h1_el.text()
                else:
                    title = await self._meta_tag(browser, "citation_title")

        # Authors
        author_els = await browser.query_selector_all(
            ".entryAuthor a, .author, .contrib-author, .NLM_contrib-group a"
        )
        authors = [await el.text() for el in author_els]
        if not authors:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract
        abstract_el = await browser.query_selector(
            ".abstractSection p, .abstract p, #abstract p"
        )
        if not abstract_el:
            abstract_el = await browser.query_selector(".hlFld-Abstract p")
        abstract = await abstract_el.text() if abstract_el else ""

        doi = await self._meta_tag(browser, "citation_doi")

        date = await self._meta_tag(browser, "citation_publication_date")
        if not date:
            date = await self._meta_tag(browser, "dc.Date")

        venue = await self._meta_tag(browser, "citation_journal_title")

        # Keywords
        kw_els = await browser.query_selector_all(
            ".abstractKeywords a, .keyword, .hlFld-KeywordText a"
        )
        keywords_seen: set[str] = set()
        keywords: list[str] = []
        for el in kw_els:
            kw = (await el.text()).rstrip(",").strip()
            if kw and kw not in keywords_seen:
                keywords_seen.add(kw)
                keywords.append(kw)

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

        # Abstract
        abstract_el = await browser.query_selector(
            ".abstractSection p, .abstract p, #abstract p"
        )
        if not abstract_el:
            abstract_el = await browser.query_selector(".hlFld-Abstract p")
        if abstract_el:
            text = await abstract_el.text()
            if text:
                sections.append(
                    Section(
                        heading="Abstract",
                        content=[ContentBlock(type="paragraph", text=text)],
                    )
                )

        # Body via evaluate — popup table extraction + querySelectorAll walk
        body_data = await browser.evaluate("""
            async () => {
                function extractTableAsText(table) {
                    const rows = [];
                    table.querySelectorAll('tr').forEach(tr => {
                        const cells = [];
                        tr.querySelectorAll('th, td').forEach(cell => {
                            cells.push(cell.textContent.trim());
                        });
                        rows.push(cells.join(' | '));
                    });
                    return rows.join('\\n');
                }

                // Capture static tables first
                const tableMap = {};
                document.querySelectorAll('table').forEach(t => {
                    if (t.querySelectorAll('tr').length < 2) return;
                    const sec = t.closest('.NLM_sec, .NLM_sec_level_1');
                    const captionEl = sec
                        ? sec.querySelector('.tableCaption, .NLM_caption, caption')
                        : null;
                    const caption = captionEl ? captionEl.textContent.trim() : '';
                    const match = caption.match(/table\\s*(\\d+)/i);
                    const key = match ? match[1] : 'static_' + Object.keys(tableMap).length;
                    tableMap[key] = { caption, text: extractTableAsText(t) };
                });

                // Extract popup tables
                const displayLinks = [];
                document.querySelectorAll('.tableView a, .tableView button').forEach(el => {
                    if (/display\\s*table/i.test(el.textContent)) {
                        const view = el.closest('.tableView');
                        const captionEl = view
                            ? view.querySelector('.tableCaption, .NLM_caption')
                            : null;
                        const caption = captionEl ? captionEl.textContent.trim() : '';
                        displayLinks.push({ el, caption });
                    }
                });

                for (let i = 0; i < displayLinks.length; i++) {
                    const link = displayLinks[i];
                    const match = link.caption.match(/table\\s*(\\d+)/i);
                    const key = match ? match[1] : 'popup_' + i;
                    if (tableMap[key]) continue;

                    const tablesBefore = document.querySelectorAll('table').length;
                    link.el.dispatchEvent(
                        new MouseEvent('click', { bubbles: true, cancelable: true, view: window })
                    );

                    // Poll up to 20 × 300ms for new table
                    let newTable = null;
                    for (let attempt = 0; attempt < 20; attempt++) {
                        await new Promise(r => setTimeout(r, 300));
                        const allTables = document.querySelectorAll('table');
                        if (allTables.length > tablesBefore) {
                            newTable = allTables[allTables.length - 1];
                            break;
                        }
                    }

                    if (newTable) {
                        const tableText = extractTableAsText(newTable);
                        if (tableText) tableMap[key] = { caption: link.caption, text: tableText };
                    }

                    // Close modal
                    const closeBtn = document.querySelector('button.modal-close')
                        || document.querySelector('button.ref-close');
                    if (closeBtn) {
                        closeBtn.dispatchEvent(
                            new MouseEvent('click', { bubbles: true, cancelable: true, view: window })
                        );
                    } else {
                        document.dispatchEvent(
                            new KeyboardEvent('keydown',
                                { key: 'Escape', keyCode: 27, bubbles: true })
                        );
                    }
                    await new Promise(r => setTimeout(r, 800));
                }

                // Build sections from body
                const sectionList = [];
                const bodyEl = document.querySelector('.hlFld-Fulltext')
                    || document.querySelector('.article__body');
                if (!bodyEl) return sectionList;

                let currentHeading = 'Introduction';
                let currentContent = [];

                function flush() {
                    if (currentContent.length > 0) {
                        sectionList.push({ heading: currentHeading, content: currentContent });
                    }
                    currentContent = [];
                }

                bodyEl.querySelectorAll(
                    'h2, h3, p, .NLM_p, table, .tableView, img[src*="cms/asset"]'
                ).forEach(el => {
                    if (el.closest('.abstractSection')) return;

                    const tag = el.tagName;
                    if ((tag === 'P' || el.classList.contains('NLM_p')) && el.closest('table')) return;
                    if ((tag === 'P' || el.classList.contains('NLM_p')) && el.closest('.tableView')) return;

                    if (tag === 'H2' || tag === 'H3') {
                        flush();
                        currentHeading = el.textContent.trim() || 'Untitled Section';
                    } else if (tag === 'TABLE') {
                        if (el.querySelectorAll('tr').length >= 2) {
                            const tableText = extractTableAsText(el);
                            if (tableText) currentContent.push({ type: 'paragraph', text: tableText });
                        }
                    } else if (el.classList.contains('tableView')) {
                        const captionEl = el.querySelector('.tableCaption, .NLM_caption');
                        const caption = captionEl ? captionEl.textContent.trim() : '';
                        const match = caption.match(/table\\s*(\\d+)/i);
                        const key = match ? match[1] : null;

                        if (key && tableMap[key]) {
                            const entry = tableMap[key];
                            const fullText = entry.caption
                                ? entry.caption + '\\n' + entry.text
                                : entry.text;
                            currentContent.push({ type: 'paragraph', text: fullText });
                        } else if (caption) {
                            currentContent.push({
                                type: 'paragraph',
                                text: caption + '\\n(Table content not available)'
                            });
                        }
                    } else if (tag === 'P' || el.classList.contains('NLM_p')) {
                        const text = el.textContent.trim();
                        if (text && text.length > 10) {
                            currentContent.push({ type: 'paragraph', text });
                        }
                    } else if (tag === 'IMG' && el.src && el.src.includes('cms/asset')) {
                        currentContent.push({ type: 'figure', figureId: el.src });
                    }
                });

                flush();
                return sectionList;
            }
        """)

        for sec_data in (body_data or []):
            content: list[ContentBlock] = []
            for block in sec_data["content"]:
                if block["type"] == "figure":
                    content.append(
                        ContentBlock(type="figure", figure_id=block["figureId"])
                    )
                else:
                    content.append(
                        ContentBlock(type="paragraph", text=block["text"])
                    )
            if content:
                sections.append(Section(heading=sec_data["heading"], content=content))

        # References
        ref_els = await browser.query_selector_all(
            ".references li, .citedByEntry, #references-section li"
        )
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
            async () => {
                const figures = [];
                const seen = new Set();
                const imgEls = document.querySelectorAll(
                    '.figureView img, img[src*="cms/asset"]'
                );

                for (const img of imgEls) {
                    const src = img.src;
                    if (!src || !src.includes('cms/asset')) continue;
                    if (seen.has(src)) continue;
                    seen.add(src);

                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                    await new Promise(r => setTimeout(r, 300));

                    const container = img.closest('.figureView') || img.closest('div');
                    let captionEl = container?.querySelector(
                        '.caption, figcaption, .NLM_caption'
                    );
                    if (!captionEl) {
                        const nextEl = container?.nextElementSibling;
                        if (nextEl && nextEl.textContent.trim().length < 300) {
                            captionEl = nextEl;
                        }
                    }
                    const caption = captionEl?.textContent?.trim() || '';

                    figures.push({ id: src, url: src, caption: caption });
                }
                return figures;
            }
        """)

        for i, item in enumerate(data or [], 1):
            figures.append(Figure(
                id=item["id"],
                url=item["url"],
                filename=f"fig{i}.png",
                caption=item["caption"],
            ))

        return figures
