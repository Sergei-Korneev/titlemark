"""Реестр экстракторов: выбираем обработчик по расширению файла.

Если расширения нет или оно неизвестное (файлы-хэши из папок загрузок),
формат определяется по сигнатуре — см. titlemark.signature.
"""

from __future__ import annotations

from pathlib import Path

from .base import Extractor
from .djvu import DjvuExtractor
from .docx import DocxExtractor
from .epub import EpubExtractor
from .fb2 import Fb2Extractor
from .mobi import MobiExtractor
from .pdf import PdfExtractor
from ..signature import detect_extension

_EXTRACTORS: list[Extractor] = [
    PdfExtractor(),
    EpubExtractor(),
    Fb2Extractor(),
    MobiExtractor(),
    DjvuExtractor(),
    DocxExtractor(),
]

_BY_EXT: dict[str, Extractor] = {}
for _ext in _EXTRACTORS:
    for _suffix in _ext.extensions:
        _BY_EXT[_suffix] = _ext


def supported_extensions() -> tuple[str, ...]:
    """Все расширения, которые умеет обрабатывать проект."""
    return tuple(sorted(_BY_EXT))


def get_extractor(path: Path) -> Extractor | None:
    """Экстрактор для файла или None, если формат не поддерживается.

    Сначала смотрим на расширение; если его нет или оно неизвестное —
    определяем формат по сигнатуре содержимого.
    """
    extractor = _BY_EXT.get(path.suffix.lower())
    if extractor is not None:
        return extractor
    return _BY_EXT.get(detect_extension(path))


__all__ = [
    "Extractor",
    "get_extractor",
    "supported_extensions",
]
