"""Определение формата файла по сигнатуре (magic bytes).

Нужно для файлов без расширения (имена-хэши в папках загрузок):
по сигнатуре понимаем, что это за документ, и подбираем экстрактор,
а при переименовании файл получает правильное расширение.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

# сколько байт читаем для определения
_HEAD_SIZE = 8192

# сигнатуры «плоских» форматов: (смещение, магические байты, расширение)
_FLAT_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"%PDF", ".pdf"),                       # PDF
    (0, b"AT&T", ".djvu"),                      # DjVu (IFF-контейнер)
    (60, b"BOOKMOBI", ".mobi"),                 # MOBI / AZW / PRC (PalmDB)
    (60, b"TEXtREAd", ".mobi"),                 # старый PalmDOC
    (0, b"\x89PNG\r\n\x1a\n", ""),              # не документ — пропускаем
    (0, b"\xff\xd8\xff", ""),                   # JPEG
    (0, b"Rar!\x1a\x07", ""),                  # RAR
    (0, b"7z\xbc\xaf\x27\x1c", ""),             # 7z
]

# типы форм IFF, которые означают DjVu
_DJVU_FORM_TYPES = (b"DJVU", b"DJVM", b"DJVI", b"BM44", b"PM44")

_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _zip_extension(path: Path) -> str:
    """Для ZIP-контейнера отличить EPUB от DOCX по составу."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = {n.lower() for n in zf.namelist()}
            if "mimetype" in names:
                try:
                    if zf.read("mimetype").startswith(b"application/epub+zip"):
                        return ".epub"
                except KeyError:
                    pass
            if "meta-inf/container.xml" in names:
                return ".epub"
            if "word/document.xml" in names:
                return ".docx"
            if any(n.endswith(".fb2") for n in names):
                return ".fb2"
    except (zipfile.BadZipFile, OSError):
        return ""
    return ""


def _xml_extension(head: bytes) -> str:
    """Определить XML-документ: FB2 (FictionBook)."""
    text = head[:_HEAD_SIZE].decode("utf-8", "replace").lower()
    if "fictionbook" in text:
        return ".fb2"
    return ""


def detect_extension(path: Path) -> str:
    """Вернуть расширение по сигнатуре («.pdf») или "" если формат не распознан.

    Пустое расширение у файла-источника тоже учитывается: функция полезна и
    для файлов с неверным/неизвестным расширением.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(_HEAD_SIZE)
    except OSError:
        return ""
    if not head:
        return ""

    for offset, magic, ext in _FLAT_SIGNATURES:
        if head[offset:offset + len(magic)] == magic:
            return ext

    # IFF-контейнер: DjVu («FORM» с типом DJVU/DJVM/…)
    if head[4:8] == b"FORM" and head[12:16] in _DJVU_FORM_TYPES:
        return ".djvu"

    if head[:4] in _ZIP_MAGIC:
        return _zip_extension(path)

    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
        return _xml_extension(head)

    return ""
