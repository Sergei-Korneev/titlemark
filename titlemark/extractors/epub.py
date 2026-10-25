"""Экстрактор EPUB: метаданные из package document (.opf)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .base import Extractor

_DC_RE = {
    "title": re.compile(r"<dc:title[^>]*>(.*?)</dc:title>", re.S | re.I),
    "creator": re.compile(r"<dc:creator[^>]*>(.*?)</dc:creator>", re.S | re.I),
    "date": re.compile(r"<dc:date[^>]*>(.*?)</dc:date>", re.S | re.I),
}


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _opf_path(zf: zipfile.ZipFile) -> str | None:
    # 1) правильный путь через container.xml
    try:
        container = zf.read("META-INF/container.xml").decode("utf-8", "replace")
        m = re.search(r'full-path="([^"]+)"', container)
        if m:
            return m.group(1)
    except KeyError:
        pass
    # 2) найти первый .opf
    for name in zf.namelist():
        if name.lower().endswith(".opf"):
            return name
    return None


class EpubExtractor(Extractor):
    extensions = (".epub",)

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        try:
            with zipfile.ZipFile(path) as zf:
                opf = _opf_path(zf)
                if not opf:
                    return "", "", ""
                data = zf.read(opf).decode("utf-8", "replace")
        except (zipfile.BadZipFile, OSError):
            return "", "", ""

        def first(key: str) -> str:
            m = _DC_RE[key].search(data)
            return _strip_tags(m.group(1)) if m else ""

        year = ""
        m = re.search(r"\b(19|20)\d{2}\b", first("date"))
        if m:
            year = m.group(0)
        return first("title"), first("creator"), year

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        # метаданных EPUB почти всегда достаточно; текст не извлекаем
        return ""
