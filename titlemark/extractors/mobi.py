"""Экстрактор MOBI: разбор PalmDB + EXTH-заголовков (без внешних библиотек)."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .base import Extractor

# типы EXTH-записей, которые нам нужны
_EXTH_AUTHOR = 100
_EXTH_PUBLISHED = 106
_EXTH_TITLE_UPDATED = 503


def _u2(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _u4(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def _decode(raw: bytes, encoding: int) -> str:
    enc = "utf-8" if encoding == 65001 else "cp1252"
    try:
        return raw.decode(enc)
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def parse_mobi(data: bytes) -> tuple[str, str, str]:
    """Вернуть (title, author, year) из байтов MOBI-файла."""
    if len(data) < 0x50 or b"MOBI" not in data[:0x200]:
        return "", "", ""

    num_records = _u2(data, 0x4C)
    if num_records == 0 or len(data) < 0x4E + 8:
        return "", "", ""
    rec0_off = _u4(data, 0x4E)
    if rec0_off >= len(data):
        return "", "", ""
    rec0 = data[rec0_off:]

    if len(rec0) < 0x5C or rec0[0x10:0x14] != b"MOBI":
        return "", "", ""
    encoding = _u4(rec0, 0x1C)

    # полное название книги хранится в самом MOBI-заголовке
    title = ""
    fullname_off = _u4(rec0, 0x54)
    fullname_len = _u4(rec0, 0x58)
    if fullname_len and fullname_off + fullname_len <= len(rec0):
        title = _decode(rec0[fullname_off:fullname_off + fullname_len], encoding).strip()

    author = year = ""
    exth_flags = _u4(rec0, 0x80) if len(rec0) >= 0x84 else 0
    if exth_flags & 0x40:
        header_len = _u4(rec0, 0x14)
        exth_off = 0x10 + header_len
        if rec0[exth_off:exth_off + 4] == b"EXTH":
            count = _u4(rec0, exth_off + 8)
            pos = exth_off + 12
            for _ in range(count):
                if pos + 8 > len(rec0):
                    break
                etype = _u4(rec0, pos)
                elen = _u4(rec0, pos + 4)
                if elen < 8 or pos + elen > len(rec0):
                    break
                value = _decode(rec0[pos + 8:pos + elen], encoding).strip("\x00").strip()
                if etype == _EXTH_TITLE_UPDATED and value:
                    title = value
                elif etype == _EXTH_AUTHOR and value:
                    author = value
                elif etype == _EXTH_PUBLISHED and value:
                    m = re.search(r"\b(19|20)\d{2}\b", value)
                    if m:
                        year = m.group(0)
                pos += elen

    return title, author, year


class MobiExtractor(Extractor):
    extensions = (".mobi", ".azw", ".prc")

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        try:
            # заголовки лежат в первых килобайтах; читаем с запасом
            with open(path, "rb") as fh:
                data = fh.read(2_000_000)
        except OSError:
            return "", "", ""
        return parse_mobi(data)

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        return ""
