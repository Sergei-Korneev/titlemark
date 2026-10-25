"""Планирование и выполнение переименования."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .extractors import get_extractor
from .models import DocumentInfo, Source
from .names import is_person_name
from .naming import build_new_name, extract_year_from_name, sanitize_component, unique_name
from .textclean import clean_author, clean_title, is_junk_title
from .titlefinder import looks_like_author


@dataclass
class RenamePlan:
    """Что сделать с одним файлом."""

    path: Path
    new_name: str = ""
    info: DocumentInfo | None = None
    status: str = "ok"          # ok | same | no-title | unsupported | error
    detail: str = ""

    @property
    def target(self) -> Path:
        return self.path.parent / self.new_name


_PERSON_GROUP_RE = re.compile(r"\s*\(([^)]{2,40})\)")


def _caps_tokens(text: str) -> int:
    """Сколько слов в строке начинается с заглавной буквы."""
    tokens = text.split()
    return sum(1 for t in tokens if t[:1].isupper())


def _personish(text: str) -> bool:
    """Похоже ли на имя автора: словарное имя, «Фамилия И. О.» или Имя Фамилия.

    Обобщённое «2–3 слова с заглавной» работает только когда вторая часть
    имени длиннее («Rethink Your Position - Katy Bowman»), чтобы не принять
    за автора «Second Edition» или «Brain An Owner's Guide».
    """
    if looks_like_author(text) or is_person_name(text):
        return True
    tokens = text.split()
    return (2 <= len(tokens) <= 3
            and _caps_tokens(text) == len(tokens)
            and all(len(t.strip(".,'’")) >= 2 for t in tokens))


def _personish_tail(tail: str, head: str) -> bool:
    """Хвост « - …» похож на имя автора (с учётом длины заголовка)."""
    if looks_like_author(tail) or is_person_name(tail):
        return True
    return _personish(tail) and len(head) > len(tail)


def _title_from_filename(path: Path) -> tuple[str, str]:
    """Запасной вариант: вытащить смысл из самого имени файла."""
    stem = path.stem
    # «03_IT_ENDS_WITH_US» → «IT_ENDS_WITH_US», но «40_алгоритмов» не трогаем:
    # цифра может быть частью названия
    stripped = re.sub(r"^\d{1,3}[_\-. ]+", "", stem)
    if stripped[:1].isupper() or not stripped[:1].isalpha():
        stem = stripped
    stem = re.sub(r"[_]+", " ", stem)

    # скобки с именем автора: «Tampa (Alissa Nutting)» → «Tampa»
    def _drop_person_group(m: re.Match) -> str:
        inner = m.group(1).strip()
        words = [w for w in inner.split() if w.isalpha()]
        if (looks_like_author(inner) or is_person_name(inner)
                or (words and 2 <= len(words) <= 3 and all(w[0].isupper() for w in words))):
            return ""
        return m.group(0)

    stem = _PERSON_GROUP_RE.sub(_drop_person_group, stem)
    stem = clean_title(stem)

    # хвостовые « - Автор»: «Rethink Your Position - Katy Bowman»
    author = ""
    while " - " in stem:
        head, tail = stem.rsplit(" - ", 1)
        head, tail = head.strip(), tail.strip()
        if _personish_tail(tail, head):
            author = clean_author(tail) or author
            stem = head
        elif (len(tail.split()) == 1 and tail[:1].isupper() and len(tail) >= 4
                and len(head.split()) >= 2 and len(head) > len(tail)):
            stem = head                       # «- Фамилия»
        else:
            break

    # формат «Автор - Название» (только если левая часть — имя)
    if " - " in stem:
        left, right = stem.split(" - ", 1)
        left, right = left.strip(), right.strip()
        if right and not _personish(right):
            # словарное/шаблонное имя — надёжный сигнал; неоднозначные
            # «2-3 слова с заглавной» требуют, чтобы название было длиннее
            strong_left = looks_like_author(left) or is_person_name(left)
            if strong_left or (_personish(left) and len(right) > len(left)):
                fb_author = clean_author(left)
                return right, fb_author or author

    m = re.search(r"\s+by\s+(.+)$", stem, re.IGNORECASE)
    if m and 1 <= len(m.group(1).split()) <= 4:
        # хвост «by …» убираем всегда; как автор он годится только если
        # прошёл очистку имени
        by_author = clean_author(m.group(1))
        return stem[: m.start()].strip(), by_author or author
    return stem, author


def _fb_richer(fb_title: str, current: str) -> bool:
    """Имя файла содержит найденное название целиком и длиннее его.

    Такой случай — когда текстовый слой дал лишь обрывок названия
    («ВЕСЬ» из «Весь Linux. Для тех, кто хочет стать профессионалом»).
    """
    if not fb_title or not current:
        return False
    fb, cur = fb_title.casefold(), current.casefold()
    if fb == cur or len(fb) < len(current) + 4 or len(current) < 3:
        return False
    return bool(re.search(rf"\b{re.escape(cur)}\b", fb))


def _weak_title(title: str) -> bool:
    """Название явно оборвано: начинается со строчной или выглядит как шифр.

    «на Python», «М. МЦНМО, 2016» — брать лучше имя файла.
    «40 алгоритмов Python» — нормальное название, цифра сама по себе не шифр.
    """
    if not title:
        return True
    if title[0].islower():
        return True
    words = title.split()
    return len(words) <= 3 and bool(re.search(r"[.,;:]", title)) \
        and any(c.isdigit() for c in title)


def _similar_title(fb_title: str, current: str, threshold: float = 0.9) -> bool:
    """Название и имя файла почти совпадают (опечатки, капс) — брать имя файла.

    Пример: библиографическая строка «ВЕСЬ LINUX. Для ТЕХ, КТО ХОЧЕТ СГАТЬ
    ПРОФЕССИОНАЛОМ» против имени файла «Весь Linux. Для тех, кто хочет
    стать профессионалом».
    """
    import difflib

    if not fb_title or not current:
        return False
    ratio = difflib.SequenceMatcher(
        None, fb_title.casefold(), current.casefold()
    ).ratio()
    return ratio >= threshold


def _strong_fb(fb_title: str) -> bool:
    """Имя файла достаточно содержательное, чтобы доверять ему больше OCR."""
    return (len(fb_title) >= 15 and len(fb_title.split()) >= 3
            and not is_junk_title(fb_title))


def _fb_covers_candidates(fb_title: str,
                          candidates: list[tuple[str, float]],
                          threshold: int = 2) -> bool:
    """Имя файла покрывает несколько сильных кандидатов из текста.

    Обложка «Linux / Книга рецептов / Все необходимое…»: имя файла
    «Linux_Книга_рецептов» содержит и «Linux», и «книга рецептов» —
    значит, оно ближе к настоящему названию, чем строка-подзаголовок.
    """
    fb = fb_title.casefold()
    hits = 0
    for cand, score in candidates:
        c = cand.strip().casefold()
        if len(c) >= 5 and score >= 3 and re.search(rf"\b{re.escape(c)}\b", fb):
            hits += 1
    return hits >= threshold


def plan_rename(
    path: Path,
    use_ocr: bool = True,
    ocr_pages: int = 2,
    include_year: bool = True,
    force_ocr: bool = False,
    ai: "AiConfig | None" = None,
    title_from_text: int = 0,
    naming_template: str | None = None,
) -> RenamePlan:
    """Разобрать файл и предложить новое имя (без изменения файлов)."""
    plan = RenamePlan(path=path)

    extractor = get_extractor(path)
    if extractor is None:
        plan.status = "unsupported"
        plan.detail = "format not supported"
        return plan

    try:
        info = extractor.extract(path, use_ocr=use_ocr, ocr_pages=ocr_pages,
                                 force_ocr=force_ocr,
                                 title_from_full_text=title_from_text)
    except Exception as exc:                    # noqa: BLE001 — не ронять пакетную обработку
        plan.status = "error"
        plan.detail = f"{type(exc).__name__}: {exc}"
        return plan
    plan.info = info

    # «заголовок» совпал с автором («Ан кур Пател» / «Анкур Пател»)
    if info.title and info.author:
        nt = re.sub(r"[\W_]+", "", info.title).casefold()
        na = re.sub(r"[\W_]+", "", info.author).casefold()
        if nt and nt == na:
            info.title = ""

    fb_title, fb_author = _title_from_filename(path)
    fb_ok = bool(fb_title) and not re.fullmatch(r"[0-9a-fA-F\-]{6,}", fb_title) \
        and not is_junk_title(fb_title)

    if not info.title:
        if fb_ok:
            info.title = fb_title
            info.title_source = Source.FILENAME
    elif fb_ok and fb_title.casefold() != info.title.casefold() and (
        _fb_richer(fb_title, info.title)
        or _weak_title(info.title)
        or _similar_title(fb_title, info.title)
        or (info.title_source is Source.OCR and _strong_fb(fb_title))
        or _fb_covers_candidates(fb_title, info.title_candidates)
    ):
        # текст/метаданные дали обрывок, шифр, кривую библиографическую
        # запись или ошибочный OCR — имя файла полнее и чище
        info.title = fb_title
        info.title_source = Source.FILENAME

    if not info.author and fb_ok and fb_author:
        info.author = fb_author
        info.author_source = Source.FILENAME

    # название не должно начинаться с повтора автора
    # («Valrog - ГОСУДАРСТВЕННОЕ…» из имени файла при авторе «Valrog»)
    if info.author and info.title:
        prefix = f"{info.author.casefold()} - "
        if info.title.casefold().startswith(prefix):
            info.title = info.title[len(prefix):].strip(" -")

    # явный флаг --ai: спросить vision-модель по обложке (ответ главнее всего)
    if ai is not None:
        from .ai import enrich_with_ai

        enrich_with_ai(path, info, ai)

    if not info.title:
        plan.status = "no-title"
        plan.detail = "title not found"
        return plan

    if not info.year and include_year:
        info.year = extract_year_from_name(path)

    # расширение целевого имени: у файла без расширения (формат определён
    # по сигнатуре) добавляем правильное
    suffix = path.suffix.lower()
    if extractor and suffix in extractor.extensions:
        target_ext = suffix
    else:
        target_ext = extractor.extensions[0] if extractor else suffix

    new_name = build_new_name(
        path,
        title=info.title,
        author=info.author,
        year=info.year if include_year else "",
        ext=target_ext,
        template=naming_template,
    )
    plan.new_name = new_name
    if new_name == path.name:
        plan.status = "same"
        plan.detail = "name already fits"
    elif not suffix:
        plan.detail = f"format detected by signature: {target_ext}"
    return plan


def iter_document_files(paths: list[Path], recursive: bool = False) -> list[Path]:
    """Собрать файлы из переданных путей (файлы и папки).

    Файлы без расширения или с неизвестным расширением попадают в подборку,
    если их формат распознан по сигнатуре.
    """
    from .extractors import supported_extensions
    from .signature import detect_extension

    exts = supported_extensions()
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            walker = path.rglob("*") if recursive else path.iterdir()
            files.extend(
                p for p in sorted(walker)
                if p.is_file() and (
                    p.suffix.lower() in exts or detect_extension(p) != ""
                )
            )
    return files


def plan_many(
    paths: list[Path],
    recursive: bool = False,
    use_ocr: bool = True,
    ocr_pages: int = 2,
    include_year: bool = True,
    force_ocr: bool = False,
    ai: "AiConfig | None" = None,
    title_from_text: int = 0,
    naming_template: str | None = None,
) -> list[RenamePlan]:
    """Разобрать все файлы и построить план переименования."""
    return [
        plan_rename(p, use_ocr=use_ocr, ocr_pages=ocr_pages,
                    include_year=include_year, force_ocr=force_ocr, ai=ai,
                    title_from_text=title_from_text,
                    naming_template=naming_template)
        for p in iter_document_files(paths, recursive=recursive)
    ]


def apply_plans(plans: list[RenamePlan]) -> list[RenamePlan]:
    """Выполнить переименование. Возвращает фактически переименованные."""
    renamed: list[RenamePlan] = []
    taken: set[str] = set()
    for plan in plans:
        if plan.status not in ("ok",) or not plan.new_name:
            continue
        if plan.new_name in taken:
            plan.new_name = unique_name(plan.target, taken)
        target = plan.path.parent / plan.new_name
        if target.exists() and target != plan.path:
            plan.new_name = unique_name(target, taken)
            target = plan.path.parent / plan.new_name
        try:
            plan.path.rename(target)
        except OSError as exc:
            plan.status = "error"
            plan.detail = str(exc)
            continue
        taken.add(plan.new_name)
        renamed.append(plan)
    return renamed


def write_csv_report(plans: list[RenamePlan], dest: Path) -> None:
    """Сохранить отчёт CSV: старое имя, новое имя, источник, статус."""
    with open(dest, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["old_name", "new_name", "title", "author", "year",
                         "title_source", "status", "detail"])
        for plan in plans:
            info = plan.info or DocumentInfo(path=plan.path)
            writer.writerow([
                plan.path.name,
                plan.new_name,
                sanitize_component(info.title),
                sanitize_component(info.author),
                info.year,
                info.title_source.value,
                plan.status,
                plan.detail,
            ])
