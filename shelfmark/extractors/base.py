"""Базовый интерфейс экстракторов и общий конвейер разбора текста."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import DocumentInfo, Source, TextQuality
from ..textclean import clean_author, clean_title, is_junk_title, text_quality
from ..titlefinder import find_author, find_title, merge_title


class Extractor(ABC):
    """Извлекает сведения о документе из файла своего формата."""

    #: расширения, которые обслуживает экстрактор
    extensions: tuple[str, ...] = ()
    #: умеет ли формат «лечить» отсутствие текста через OCR
    ocr_capable: bool = False

    @abstractmethod
    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        """Вернуть (title, author, year) из метаданных файла."""

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        """Вернуть текст первых страниц (пустая строка, если формат не умеет)."""
        return ""

    # ------------------------------------------------------------------
    def extract(self, path: Path, use_ocr: bool = True, ocr_pages: int = 2,
                force_ocr: bool = False,
                title_from_full_text: int = 0) -> DocumentInfo:
        """Полный разбор файла: метаданные → текстовый слой → (опц.) OCR.

        force_ocr=True — распознать первые страницы через OCR обязательно
        и использовать именно этот текст (штатный текстовый слой бывает
        кривым: неверная кодировка, раздробленные слова).

        title_from_full_text=N — название собирается из ВСЕГО текста первых
        N страниц без спецсимволов, а не из отдельных строк-кандидатов.
        """
        info = DocumentInfo(path=path, format=path.suffix.lower().lstrip("."))

        meta_title, meta_author, year = self.read_metadata(path)
        # мусорность проверяем по СЫРОЙ строке метаданных («Pamyat_text 02.indd»)
        # и ещё раз после очистки («… @bookinier», «… издательство …»)
        if meta_title and not is_junk_title(meta_title):
            meta_title = clean_title(meta_title)
            if meta_title and not is_junk_title(meta_title):
                info.title = meta_title
                info.title_source = Source.METADATA
        meta_author = clean_author(meta_author)
        if meta_author:
            info.author = meta_author
            info.author_source = Source.METADATA
        if year:
            info.year = year

        pages = title_from_full_text if title_from_full_text > 0 else 3
        text = self.read_text(path, max_pages=pages)
        quality = text_quality(text)
        info.text_snippet = text[:400]
        used_text, used_source = text, Source.TEXT

        used_forced_ocr = False
        if force_ocr and self.ocr_capable:
            from ..ocr import ocr_first_pages

            ocr_text = ocr_first_pages(path, pages=ocr_pages)
            if ocr_text.strip():
                info.warnings.append("OCR forced by --force-ocr")
                self._fill_from_text(info, ocr_text, source=Source.OCR, override=True)
                used_text, used_source = ocr_text, Source.OCR
                used_forced_ocr = True
            else:
                info.warnings.append("OCR produced no text — text layer used")

        if not used_forced_ocr:
            if quality is TextQuality.GOOD:
                self._fill_from_text(info, text, source=Source.TEXT)
            elif use_ocr and self.ocr_capable:
                from ..ocr import ocr_first_pages

                ocr_text = ocr_first_pages(path, pages=ocr_pages)
                if ocr_text.strip():
                    info.warnings.append("text layer missing/broken — OCR used")
                    self._fill_from_text(info, ocr_text, source=Source.OCR)
                    used_text, used_source = ocr_text, Source.OCR
                elif not info.title:
                    info.warnings.append("no text layer and OCR failed")

        # режим «название из всего текста»: склеиваем содержательные строки
        if title_from_full_text > 0 and used_text.strip():
            from ..titlefinder import full_text_title

            full_title = full_text_title(used_text, exclude_author=info.author)
            if full_title:
                info.title = full_title
                info.title_source = used_source
                info.warnings.append(
                    f"title built from the full text of the first "
                    f"{title_from_full_text} page(s) (--title-from-text)")

        return info

    # ------------------------------------------------------------------
    def _fill_from_text(self, info: DocumentInfo, text: str,
                        source: Source = Source.TEXT,
                        override: bool = False) -> None:
        """Заполнить title/author из текста, если метаданных не хватило.

        override=True — текст главнее метаданных (принудительный OCR).
        """
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return

        title, _score, candidates = find_title(lines)
        info.title_candidates = candidates
        if title:
            title = clean_title(merge_title(lines, title))
        if title and (override or not info.title
                      or info.title_source is not Source.METADATA):
            info.title = title
            info.title_source = source

        # строки, вошедшие в название, уже не автор
        author = clean_author(find_author(lines, exclude_title=title))
        if author and (override or not info.author
                       or info.author_source is not Source.METADATA):
            info.author = author
            info.author_source = source
