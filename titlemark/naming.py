"""Построение нового имени файла по шаблону: «{author} - {title} [{year}]»."""

from __future__ import annotations

import re
import string
from pathlib import Path

# символы, запрещённые в именах файлов (в т. ч. для переносимости на Windows)
_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WS_RE = re.compile(r"\s+")

# лимиты: файловая система принимает не больше 255 БАЙТ на компонент пути,
# а кириллица занимает 2 байта — оставляем запас
MAX_NAME_BYTES = 200

# плейсхолдеры шаблона имени
TEMPLATE_FIELDS = ("author", "title", "year")

DEFAULT_TEMPLATE = "{author} - {title} [{year}]"


def validate_template(template: str) -> str | None:
    """Проверить шаблон имени. None — всё в порядке, иначе текст ошибки."""
    try:
        fields = [f for _lit, f, _spec, _conv in string.Formatter().parse(template)
                  if f]
    except ValueError as exc:
        return f"invalid template: {exc}"
    known = {f.split(".")[0].split("[")[0] for f in fields}
    unknown = sorted(known - set(TEMPLATE_FIELDS))
    if unknown:
        return (f"unknown placeholder(s): {', '.join(unknown)} "
                f"(available: {', '.join('{%s}' % t for t in TEMPLATE_FIELDS)})")
    return None


def sanitize_component(text: str) -> str:
    """Убрать запрещённые символы и схлопнуть пробелы."""
    t = _FORBIDDEN_RE.sub(" ", text or "")
    t = _WS_RE.sub(" ", t).strip(" .")
    return t


def _tidy(stem: str) -> str:
    """Подчистить пустые места от подстановки пустых значений.

    «{author} - {title}» без автора → « - Название» → «Название»;
    «{title} [{year}]» без года → «Название []» → «Название»;
    «{title}-{year}» без года → «Название-» → «Название».
    """
    for _ in range(2):
        stem = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}", "", stem)   # пустые скобки
        stem = _WS_RE.sub(" ", stem)
    # висячие разделители по краям: «Название-», «-Название», «_Название»
    stem = stem.strip(" \t-_–—|,;:")
    stem = re.sub(r"[\s_\-–—|,;:]+$", "", stem)
    stem = re.sub(r"^[\s_\-–—|,;:]+", "", stem)
    return stem.strip()


def _truncate_bytes(text: str, max_bytes: int) -> str:
    """Обрезать строку по границе слов, не превышая лимит байт UTF-8."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    cut = raw[:max_bytes].decode("utf-8", errors="ignore")
    # граница слова
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .,-–—") + "…"


def build_new_name(
    path: Path,
    title: str,
    author: str = "",
    year: str = "",
    max_bytes: int = MAX_NAME_BYTES,
    ext: str | None = None,
    template: str | None = None,
) -> str:
    """Собрать новое имя файла по шаблону (расширение дописывается само).

    Шаблон по умолчанию: «{author} - {title} [{year}]». Пустые значения
    убираются вместе со своими разделителями. Если название не найдено —
    возвращается исходное имя.

    `ext` — расширение для целевого имени; используется, когда у исходного
    файла расширения нет (формат определён по сигнатуре).
    """
    ext = (ext if ext is not None else path.suffix).lower()
    if not title:
        return path.name

    # год не дублируем, если он уже есть в названии или авторе
    if year and year in f"{author} {title}":
        year = ""

    tpl = template or DEFAULT_TEMPLATE
    stem = tpl.format(author=author, title=title, year=year)
    stem = _tidy(sanitize_component(stem))
    if not stem:
        return path.name

    stem = _truncate_bytes(stem, max_bytes - len(ext.encode("utf-8")))
    return f"{stem}{ext}"


def unique_name(target: Path, taken: set[str] | None = None) -> str:
    """Не занято ли целевое имя; если занято — добавить « (2)», « (3)»…"""
    taken = taken or set()
    stem, ext = target.stem, target.suffix
    candidate = target.name
    i = 2
    while candidate in taken or (target.parent / candidate).exists():
        candidate = f"{stem} ({i}){ext}"
        i += 1
    return candidate


def extract_year_from_name(path: Path) -> str:
    """Вытащить год из исходного имени файла (последний вариант)."""
    m = re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", path.stem)
    return m.group(0) if m else ""
