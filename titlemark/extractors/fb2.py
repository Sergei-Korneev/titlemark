"""Экстрактор FB2: description/title-info/book-title и author."""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree

from .base import Extractor


def _local(tag: str) -> str:
    """Тег без пространства имён (FB2 может использовать xmlns)."""
    return tag.rsplit("}", 1)[-1].lower()


def _text_of(elem) -> str:
    return "".join(elem.itertext()).strip()


class Fb2Extractor(Extractor):
    extensions = (".fb2",)

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        try:
            tree = ElementTree.parse(path)
        except (ElementTree.ParseError, OSError):
            return "", "", ""

        title = author = year = ""
        book_title_info = None

        for elem in tree.iter():
            name = _local(elem.tag)
            if name == "title-info" and book_title_info is None:
                book_title_info = elem

        if book_title_info is not None:
            for child in book_title_info:
                cname = _local(child.tag)
                if cname == "book-title":
                    title = _text_of(child)
                elif cname == "author":
                    author = self._author_name(child)
                elif cname == "date":
                    m = re.search(r"\b(19|20)\d{2}\b", _text_of(child))
                    if m:
                        year = m.group(0)

        if not title:
            for elem in tree.iter():
                if _local(elem.tag) == "book-title":
                    title = _text_of(elem)
                    break
        return title, author, year

    @staticmethod
    def _author_name(author_elem) -> str:
        parts: dict[str, str] = {}
        for child in author_elem:
            parts[_local(child.tag)] = _text_of(child)
        first = parts.get("first-name", "")
        middle = parts.get("middle-name", "")
        last = parts.get("last-name", "")
        nick = parts.get("nickname", "")

        # инициалы: «Ю» + «А» + «Штюрмер» → «Штюрмер Ю. А.»
        if first and len(first) <= 2 and last:
            initials = first if first.endswith(".") else first + "."
            if middle:
                initials += " " + (middle if middle.endswith(".") else middle + ".")
            return f"{last} {initials}".strip()

        name = " ".join(p for p in (first, middle, last) if p).strip()
        return name or nick

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        return ""
