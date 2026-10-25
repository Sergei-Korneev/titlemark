"""OCR первых страниц: рендер страницы + tesseract.

PDF рендерится через pdftoppm, DjVu — через ddjvu (djvulibre); для DjVu без
ddjvu OCR недоступен (PIL такие страницы не открывает).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def available() -> bool:
    return bool(shutil.which("tesseract")
                and (shutil.which("pdftoppm") or shutil.which("ddjvu")))


def _run(cmd: list[str], timeout: int) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return res.stdout.decode("utf-8", errors="replace")


def _is_djvu(path: Path) -> bool:
    if path.suffix.lower() == ".djvu":
        return True
    from .signature import detect_extension
    return detect_extension(path) == ".djvu"


def render_page(path: Path, page: int, out_dir: Path, dpi: int = 150) -> Path | None:
    """Отрендерить одну страницу документа; вернуть путь к картинке или None."""
    if _is_djvu(path):
        exe = shutil.which("ddjvu")
        if not exe:
            return None
        out = out_dir / f"p{page}.tif"
        _run([exe, f"-page={page}", "-format=tiff", str(path), str(out)], timeout=120)
        return out if out.exists() else None

    exe = shutil.which("pdftoppm")
    if not exe:
        return None
    out_prefix = out_dir / f"p{page}"
    _run([exe, "-f", str(page), "-l", str(page), "-r", str(dpi),
          "-png", "-singlefile", str(path), str(out_prefix)], timeout=120)
    out = out_dir / f"p{page}.png"
    return out if out.exists() else None


def ocr_first_pages(path: Path, pages: int = 2, lang: str = "rus+eng",
                    dpi: int = 150) -> str:
    """Распознать первые `pages` страниц документа и вернуть текст.

    Если tesseract или рендерер недоступны — возвращается "".
    """
    if not available():
        return ""

    texts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="shelfmark_ocr_") as tmp:
        tmpdir = Path(tmp)
        for page in range(1, pages + 1):
            img = render_page(path, page, tmpdir, dpi=dpi)
            if img is None:
                break
            text = _run(["tesseract", str(img), "stdout", "-l", lang], timeout=180)
            if text.strip():
                texts.append(text)
            if len("".join(texts)) > 2000:      # текста достаточно
                break
    return "\n".join(texts)
