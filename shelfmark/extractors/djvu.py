"""Экстрактор DJVU: аннотации ANTa + текстовый слой через djvulibre.

DjVu хранит текст в сжатых чанках TXTz (BZZ), извлечь их без djvulibre
нельзя; если утилиты `djvutxt`/`ddjvu` установлены (пакет djvulibre),
текст берётся из них, а для сканов работает OCR через ddjvu + tesseract.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .base import Extractor

_ANNOTATION_RES = [
    (re.compile(r'\(\s*title\s+"([^"]*)"\s*\)', re.I), "title"),
    (re.compile(r'\(\s*author\s+"([^"]*)"\s*\)', re.I), "author"),
    (re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S), "title"),
    (re.compile(r"<author[^>]*>(.*?)</author>", re.I | re.S), "author"),
]


def _chunks(data: bytes, pos: int, end: int):
    """Обойти чанки IFF: id(4) + длина(4, BE) + данные (с паддингом до чётности)."""
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        length = int.from_bytes(data[pos + 4:pos + 8], "big")
        body_start = pos + 8
        body_end = body_start + length
        if length < 0 or body_end > end:
            return
        yield cid, data[body_start:body_end]
        pos = body_end + (length & 1)


def find_annotations(data: bytes) -> dict[str, str]:
    """Найти первый чанк ANTa и вытащить из него title/author."""

    def walk(buf: bytes, pos: int, end: int) -> dict[str, str]:
        for cid, body in _chunks(buf, pos, end):
            if cid == b"FORM" and len(body) >= 4:
                found = walk(body, 4, len(body))     # вложенные чанки формы
                if found:
                    return found
            elif cid == b"ANTa":
                text = body.decode("utf-8", "replace")
                result: dict[str, str] = {}
                for rx, key in _ANNOTATION_RES:
                    m = rx.search(text)
                    if m and not result.get(key):
                        result[key] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if result:
                    return result
        return {}

    start = 4 if data[:4] == b"AT&T" else 0
    return walk(data, start, len(data))


def _run(cmd: list[str], timeout: int = 120) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return res.stdout.decode("utf-8", errors="replace")


def djvulibre_text(path: Path, max_pages: int = 3) -> str:
    """Текст первых страниц через djvutxt (djvulibre); "" если утилиты нет.

    Разделитель страниц — form feed (\f).
    """
    exe = shutil.which("djvutxt")
    if not exe:
        return ""
    out = _run([exe, str(path)])
    if not out.strip():
        return ""
    pages = out.split("\f")
    return "\n".join(pages[:max_pages])


class DjvuExtractor(Extractor):
    extensions = (".djvu",)
    ocr_capable = True          # рендер страниц через ddjvu + tesseract

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        try:
            with open(path, "rb") as fh:
                data = fh.read(4_000_000)
        except OSError:
            return "", "", ""
        found = find_annotations(data)
        return found.get("title", ""), found.get("author", ""), ""

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        return djvulibre_text(path, max_pages=max_pages)
