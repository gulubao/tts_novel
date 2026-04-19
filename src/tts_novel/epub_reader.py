"""EPUB reader: document items to ordered plain-text chapters."""

from dataclasses import dataclass
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub


@dataclass(frozen=True)
class Chapter:
    index: int
    title: str
    text: str


def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    heading = soup.find(["h1", "h2", "h3"])
    if heading is None:
        return fallback
    return heading.get_text(" ", strip=True) or fallback


def _extract_paragraphs(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style"]):
        tag.decompose()
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    return "\n\n".join(paragraphs)


def read_epub(path: Path) -> list[Chapter]:
    book = epub.read_epub(str(path))
    chapters: list[Chapter] = []
    idx = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "lxml-xml")
        text = _extract_paragraphs(soup)
        if not text:
            continue
        title = _extract_title(soup, fallback=f"doc-{idx}")
        chapters.append(Chapter(index=idx, title=title, text=text))
        idx += 1
    return chapters
