"""Эвристики выбора заголовка и автора из текста первых страниц.

Идея простая: заголовок на титульной странице обычно
  * ближе к началу текста,
  * набран ЗАГЛАВНЫМИ или Title Case,
  * центрирован (в выкладке pdftotext -layout остаются отступы),
  * не заканчивается точкой/двоеточием,
  * не похож на имя автора, ISBN, колонтитул.
"""

from __future__ import annotations

import re

from .names import is_person_name
from .textclean import (
    clean_title,
    is_author_line,
    is_junk_title,
    is_service_line,
    strip_special,
)

# --- паттерны имён ----------------------------------------------------------

# «Фамилия И. О.» / «Фамилия, И. О.» / «И. О. Фамилия»
_INITIALS_NAME_RE = re.compile(
    r"^\s*[А-ЯЁA-Z][а-яёa-z]+\s*,?\s+[А-ЯЁA-Z]\.\s*[А-ЯЁA-Z]\.\s*$"
)
_INITIALS_FIRST_RE = re.compile(
    r"^\s*([А-ЯЁA-Z]\.\s*){1,2}[А-ЯЁ][а-яё]+"
    r"(\s*,\s*([А-ЯЁA-Z]\.\s*){1,2}[А-ЯЁ][а-яё]+)*\s*$"
)
_EN_BY_RE = re.compile(r"^\s*by\s+[A-Z][A-Za-z'’\-.]+(\s+[A-Z][A-Za-z'’\-.]+){1,3}\s*$")
_RU_AUTHOR_LABEL_RE = re.compile(r"^\s*(автор|author|редактор|перевод)\s*[:—-]", re.IGNORECASE)
# библиографическая запись «Фамилия, Имя» / «Фамилия, И. О.»
_RU_SURNAME_FIRST_RE = re.compile(
    r"^\s*[А-ЯЁA-Z][а-яёa-z]+(-[а-яёa-z]+)?\s*,\s*"
    r"([А-ЯЁA-Z][а-яёa-z]+|[А-ЯЁA-Z]\.\s*[А-ЯЁA-Z]\.)\s*$"
)
_RU_NAME_RE = re.compile(
    r"^\s*[А-ЯЁ][а-яё]+(-[а-яё]+)*\s+[А-ЯЁ][а-яё]+(-[а-яё]+)*"
    r"(\s+[А-ЯЁ][а-яё]+(-[а-яё]+)*)?\s*$"
)
# 2–3 слова целиком ЗАГЛАВНЫМИ: либо имя («АРТУР ДУМЧЕВ»), либо короткий
# заголовок («DARK MATTER») — неоднозначно, обрабатывается отдельно
_CAPS_NAME_RE = re.compile(r"^\s*([А-ЯЁA-Z]{2,}\s+){1,2}[А-ЯЁA-Z]{2,}\s*$")


def looks_like_author_strict(text: str) -> bool:
    """Строка с высокой достоверностью — имя автора (не заголовок)."""
    t = text.strip()
    if not t:
        return False
    return bool(
        is_author_line(t)
        or _INITIALS_NAME_RE.match(t)
        or _INITIALS_FIRST_RE.match(t)
        or _RU_SURNAME_FIRST_RE.match(t)
        or _EN_BY_RE.match(t)
        or _RU_AUTHOR_LABEL_RE.match(t)
        or _RU_NAME_RE.match(t)
    )


def looks_like_author(text: str) -> bool:
    """Строка похожа на имя автора (включая неоднозначные ЗАГЛАВНЫЕ)."""
    return (looks_like_author_strict(text)
            or is_person_name(text)
            or bool(_CAPS_NAME_RE.match(text.strip())))


def extract_author_from_line(text: str) -> str:
    """Достать имя из строки-подписи автора (убрать «Автор:», «by»)."""
    t = text.strip()
    t = re.sub(r"^\s*(by|author|автор|редактор|перевод)\s*[:—-]?\s*", "", t, flags=re.IGNORECASE)
    return t.strip(" .,-–—")


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _title_case_ratio(text: str) -> float:
    words = [w for w in re.split(r"[\s\-–—:,.]+", text) if w]
    words = [w for w in words if w.isalpha()]
    if not words:
        return 0.0
    titled = sum(1 for w in words if w[0].isupper())
    return titled / len(words)


def score_title_candidate(line: str, index: int, total: int,
                          allow_person: bool = False) -> float:
    """Оценка строки как возможного заголовка. -inf — не подходит вовсе.

    allow_person=False — строки, похожие на имя автора, отбрасываются
    полностью (основной проход); True — участвуют со штрафом (запасной
    проход для обложек вида «АННА КАРЕНИНА / ЛЕВ ТОЛСТОЙ»).
    """
    text = line.strip()
    n = len(text)
    if n < 3 or n > 130:
        return float("-inf")

    letters = [c for c in text if c.isalpha()]
    if len(letters) < 2:
        return float("-inf")
    digits = sum(c.isdigit() for c in text)
    if digits / n > 0.35:
        return float("-inf")
    if is_junk_title(text) or is_service_line(text) or looks_like_author_strict(text):
        return float("-inf")
    # словарное имя — почти наверняка подпись автора; неоднозначные
    # ЗАГЛАВНЫЕ строки отбрасываем только в запасном проходе
    person_like = is_person_name(text) or bool(_CAPS_NAME_RE.match(text))
    if is_person_name(text) and not allow_person:
        return float("-inf")

    words = text.split()
    score = 0.0

    # регистр
    caps = _caps_ratio(text)
    if caps > 0.7:
        score += 3.0
    elif caps > 0.4:
        score += 1.5
    tc = _title_case_ratio(text)
    if 0.5 <= tc <= 1.0:
        score += 1.2

    # неоднозначная строка: имя автора или короткий заголовок
    if person_like:
        score -= 2.5

    # позиция: чем раньше, тем вероятнее титул
    if total > 1:
        score += 2.0 * (1.0 - index / max(total - 1, 1))
    if index == 0:
        score += 0.8

    # выравнивание по центру (в -layout остаются отступы слева/справа)
    if line[:1] == " " and len(line) - len(line.lstrip()) > 2:
        score += 1.0

    # длина: оптимум 2–9 слов
    wc = len(words)
    if wc < 2:
        score -= 1.0
    elif 2 <= wc <= 9:
        score += 1.0
    elif wc > 12:
        score -= 1.5

    # пунктуация
    if text.endswith((".", "!", ";")):
        score -= 0.7
    if text.endswith("?"):
        score += 0.3          # вопросительные заголовки — норма
    if text.endswith(":"):
        score -= 1.5          # скорее заголовок раздела
    if text.endswith((",", "-", "–")):
        score -= 1.0          # обрыв строки-подзаголовка

    # прочие маркеры
    if re.search(r"\b(часть|part|том|volume|vol\.|chapter|глава)\b", text, re.IGNORECASE):
        if n < 30:
            score -= 1.0
    return score


def find_title(lines: list[str]) -> tuple[str, float, list[tuple[str, float]]]:
    """Лучший кандидат в заголовки среди строк текста.

    Сначала ищем среди «не-имён»; если таких строк нет (обложка вида
    «АННА КАРЕНИНА / ЛЕВ ТОЛСТОЙ») — повторяем с учётом имён.

    Возвращает (заголовок, оценка, все_кандидаты_по_убыванию).
    """
    if not lines:
        return "", float("-inf"), []

    considered = lines[:40]              # титул живёт в начале документа
    all_scored: list[tuple[str, float]] = []

    for allow_person in (False, True):
        base = [
            score_title_candidate(ln, i, len(considered), allow_person=allow_person)
            for i, ln in enumerate(considered)
        ]
        scored: list[tuple[str, float]] = []
        for i, line in enumerate(considered):
            s = base[i]
            if s == float("-inf"):
                continue
            # строка начинает блок текста (после пустоты/слабой строки) —
            # так выглядит первая строка титула
            prev = base[i - 1] if i > 0 else float("-inf")
            if prev == float("-inf") or prev < 3.0:
                s += 1.5
            scored.append((line.strip(), round(s, 2)))
        scored.sort(key=lambda x: x[1], reverse=True)
        if not all_scored:
            all_scored = scored
        if scored and scored[0][1] >= 2.0:
            return scored[0][0], scored[0][1], (scored + all_scored)[:10]

    best = all_scored[0][1] if all_scored else float("-inf")
    return "", best, all_scored[:10]


def find_author(lines: list[str], exclude_title: str = "") -> str:
    """Лучший кандидат в авторы среди строк текста (первые 30 строк).

    Строки, вошедшие в название (exclude_title), пропускаются.
    """
    def excluded(line: str) -> bool:
        t = line.strip()
        return bool(t and exclude_title and t in exclude_title)

    head = [ln for ln in lines[:30]]

    # первый проход: имена из словаря («АРТУР ДУМЧЕВ», «Colleen Hoover»).
    # если строк с именами несколько (обложка «Заголовок / Автор»),
    # автором считаем ПОСЛЕДНЮЮ
    persons = [ln for ln in head if not excluded(ln) and is_person_name(ln)]
    if persons:
        return extract_author_from_line(persons[-1])

    # второй проход: строгие признаки (инициалы, «by», «Автор:»)
    for line in head:
        if not excluded(line) and looks_like_author_strict(line):
            name = extract_author_from_line(line)
            if len(name.split()) >= 2 or re.search(r"[А-ЯЁA-Z]\.", name):
                return name

    # третий проход: неоднозначные ЗАГЛАВНЫЕ имена, не вошедшие в название
    caps_names = [ln for ln in head
                  if not excluded(ln) and _CAPS_NAME_RE.match(ln.strip())]
    if caps_names:
        return extract_author_from_line(caps_names[-1])
    return ""


# объединение заголовка с продолжением на следующих строках
_CONTINUATION_RE = re.compile(r"^[a-zа-яё0-9]")
_MERGE_MAX_CHARS = 58
_MERGE_MAX_LINES = 3
_MERGE_MAX_LINE_CHARS = 48


def _norm_name(text: str) -> str:
    return re.sub(r"[\W_]+", "", text or "").casefold()


def full_text_title(text: str, exclude_author: str = "") -> str:
    """Собрать название из ВСЕГО текста страницы (--title-from-text).

    Кандидаты эвристик часто бывают лишь кусочками названия; здесь все
    содержательные строки страницы склеиваются в одно название, а
    спецсимволы вырезаются. Строки-служебки (ISBN, издательства, города,
    колонтитулы) и строка автора отбрасываются.
    """
    from .textclean import strip_special

    author_norm = _norm_name(exclude_author)
    kept: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 2 or is_junk_title(line) or is_service_line(line):
            continue
        if looks_like_author_strict(line):
            continue
        if author_norm and _norm_name(line) == author_norm:
            continue
        kept.append(line)

    merged = strip_special(" ".join(kept))
    return clean_title(merged)


def merge_title(lines: list[str], title: str) -> str:
    """Если заголовок разбит на несколько строк — попробовать склеить.

    Склеиваются только короткие продолжения (подзаголовок), не дальше
    строки-автора и не длиннее ~55 символов.
    """
    if not title:
        return title

    for i, line in enumerate(lines[:40]):
        if line.strip() != title:
            continue
        merged = title
        for j in range(1, _MERGE_MAX_LINES):
            if i + j >= len(lines):
                break
            nxt = lines[i + j].strip()
            if (not nxt or len(nxt) > _MERGE_MAX_LINE_CHARS
                    or len(merged) + len(nxt) + 1 > _MERGE_MAX_CHARS
                    or looks_like_author_strict(nxt) or is_person_name(nxt)
                    or is_service_line(nxt) or is_junk_title(nxt)
                    or nxt.endswith((".", "!", ";", ":"))):
                break
            if _CONTINUATION_RE.match(nxt) or _title_case_ratio(nxt) >= 0.6:
                merged = f"{merged} {nxt}"
            else:
                break
        return merged
    return title
