"""OCR первых страниц PDF через pdftoppm + tesseract (для сканов)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def available() -> bool:
    return bool(shutil.which("pdftoppm") and shutil.which("tesseract"))


def _run(cmd: list[str], timeout: int) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return res.stdout.decode("utf-8", errors="replace")


def ocr_first_pages(path: Path, pages: int = 2, lang: str = "rus+eng", dpi: int = 150) -> str:
    """Распознать первые `pages` страниц PDF и вернуть текст.

    Если tesseract/pdftoppm недоступны — возвращается "".
    """
    if not available():
        return ""

    texts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="shelfmark_ocr_") as tmp:
        tmpdir = Path(tmp)
        for page in range(1, pages + 1):
            out_prefix = tmpdir / f"p{page}"
            _run(
                ["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi),
                 "-png", "-singlefile", str(path), str(out_prefix)],
                timeout=120,
            )
            img = tmpdir / f"p{page}.png"
            if not img.exists():
                break
            text = _run(["tesseract", str(img), "stdout", "-l", lang], timeout=180)
            if text.strip():
                texts.append(text)
            if len("".join(texts)) > 2000:      # текста достаточно
                break
    return "\n".join(texts)
