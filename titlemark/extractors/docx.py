"""Экстрактор DOCX: docProps/core.xml + первые абзацы word/document.xml."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .base import Extractor

_TAG_RE = re.compile(r"<[^>]+>")
_WT_RE = re.compile(r"<w:t[^>]*>(.*?)</w:t>", re.S)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


class DocxExtractor(Extractor):
    extensions = (".docx",)

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        try:
            with zipfile.ZipFile(path) as zf:
                try:
                    core = zf.read("docProps/core.xml")
                except KeyError:
                    return "", "", ""
        except (zipfile.BadZipFile, OSError):
            return "", "", ""

        try:
            root = ElementTree.fromstring(core)
        except ElementTree.ParseError:
            return "", "", ""

        title = author = year = ""
        for elem in root.iter():
            name = _local(elem.tag)
            text = (elem.text or "").strip()
            if not text:
                continue
            if name == "title" and not title:
                title = text
            elif name == "creator" and not author:
                author = text
            elif name == "created":
                m = re.search(r"\b(19|20)\d{2}\b", text)
                if m:
                    year = m.group(0)
        return title, author, year

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        try:
            with zipfile.ZipFile(path) as zf:
                doc = zf.read("word/document.xml").decode("utf-8", "replace")
        except (zipfile.BadZipFile, KeyError, OSError):
            return ""
        parts = _WT_RE.findall(doc)
        if parts:
            return " ".join(_TAG_RE.sub("", p) for p in parts[:200])
        return _TAG_RE.sub(" ", doc[:20000])
