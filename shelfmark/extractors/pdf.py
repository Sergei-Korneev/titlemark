"""Экстрактор PDF: poppler (pdfinfo/pdftotext) + OCR как запасной путь."""

from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from .base import Extractor

_PDFINFO_RE = re.compile(r"^([^:]+):\s*(.*)$")


@lru_cache(maxsize=1)
def _tools() -> dict[str, str | None]:
    return {
        "pdfinfo": shutil.which("pdfinfo"),
        "pdftotext": shutil.which("pdftotext"),
        "pdftoppm": shutil.which("pdftoppm"),
    }


def _run(cmd: list[str], timeout: int = 60) -> str:
    try:
        res = subprocess.run(
            cmd, capture_output=True, timeout=timeout, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return res.stdout.decode("utf-8", errors="replace")


def pdfinfo_fields(path: Path) -> dict[str, str]:
    """Свойства PDF в виде словаря {'Title': ..., 'Author': ...}."""
    exe = _tools()["pdfinfo"]
    if not exe:
        return {}
    out = _run([exe, str(path)])
    fields: dict[str, str] = {}
    for line in out.splitlines():
        m = _PDFINFO_RE.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def _year_from_pdfinfo(fields: dict[str, str]) -> str:
    for key in ("CreationDate", "ModDate"):
        m = re.search(r"(19|20)\d{2}", fields.get(key, ""))
        if m:
            return m.group(0)
    return ""


class PdfExtractor(Extractor):
    extensions = (".pdf",)
    ocr_capable = True

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        fields = pdfinfo_fields(path)
        return (
            fields.get("Title", ""),
            fields.get("Author", ""),
            _year_from_pdfinfo(fields),
        )

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        exe = _tools()["pdftotext"]
        if not exe:
            return ""
        out = _run(
            [exe, "-f", "1", "-l", str(max_pages), "-layout", "-q", str(path), "-"],
            timeout=90,
        )
        # убрать символы, полученные из-за неверной кодировки ToUnicode,
        # они всё равно не помогут в поиске заголовка
        return out.replace("\x0c", "\n")
