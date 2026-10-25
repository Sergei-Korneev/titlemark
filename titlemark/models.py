"""Модели данных проекта titlemark."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Source(str, Enum):
    """Откуда получены данные о документе."""

    METADATA = "metadata"      # свойства/метаданные файла
    TEXT = "text"              # текстовый слой документа
    OCR = "ocr"                # OCR отсканированных страниц
    AI = "ai"                  # vision-LLM по обложке (--ai)
    FILENAME = "filename"      # разбор текущего имени файла
    NONE = "none"              # ничего не найдено


class TextQuality(str, Enum):
    """Качество извлечённого текста."""

    GOOD = "good"
    GARBAGE = "garbage"        # кракозябры из-за нестандартной кодировки шрифтов
    EMPTY = "empty"            # текстового слоя нет (скан)


@dataclass
class DocumentInfo:
    """Результат извлечения сведений о документе."""

    path: Path
    format: str = ""
    title: str = ""
    author: str = ""
    year: str = ""
    title_source: Source = Source.NONE
    author_source: Source = Source.NONE
    warnings: list[str] = field(default_factory=list)
    # отладочная информация для --verbose
    text_snippet: str = ""
    title_candidates: list[tuple[str, float]] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        """Есть ли хоть какой-то полезный результат."""
        return bool(self.title or self.author)
