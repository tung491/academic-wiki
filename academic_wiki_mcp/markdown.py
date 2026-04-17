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
