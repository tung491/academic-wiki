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
