"""Очистка и оценка текста: фильтр мусорных заголовков, детект кракозябр.

Здесь нет привязки к формату файла — только работа со строками.
"""

from __future__ import annotations

import re
import unicodedata

from .models import TextQuality

# ---------------------------------------------------------------------------
# Паттерны «мусорных» заголовков, которые встречаются в свойствах файлов
# ---------------------------------------------------------------------------

_JUNK_TITLE_PATTERNS = [
    # артефакты верстки и конвертации
    r"^layout\s*\d*$",
    r"^untitled", r"^document\s*\d*$", r"^new\s+microsoft", r"^microsoft\s+word",
    r"^scan(ned)?(\s+document)?\s*\d*$", r"^image\s*\d*$", r"^file\s*\d*$",
    r"^page\s*\d*$", r"^ocr\s*\d*$", r"^tmp$", r"^temp$",
    # имя выходного файла вместо названия
    r"\.(docx?|rtf|odt|indd|txt|html?|pptx?|xlsx?|pdf|djvu|epub|fb2)$",
    r"^[0-9a-f]{8,}$",               # хэш
    r"^\d{6,}$",                     # длинный номер (id загрузки)
    r"^[0-9a-f-]{20,}$",             # uuid
    # служебные надписи
    r"^содержание$", r"^оглавление$", r"^title$", r"^cover$",
    r"^title\.\d+", r"^aspose\b", r"\baspose\b",
    # нумерованные строки-разделы: «1. ВВЕДЕНИЕ», «2.3 ОСНОВНЫЕ ПОНЯТИЯ»
    # (только ЗАГЛАВНЫЕ — регистр важен, поэтому (?-i:...))
    r"^\d+(\.\d+)*\.?\s+((?-i:[А-ЯЁA-Z]){2,}\s*){1,4}$",
    r"^a\s+(novel|book|memoir|thriller)$", r"^(роман|повесть|учебное пособие)$",
    r"^(слайд|slide|таблица|table|рисунок|figure|рис\.)\s*\d*$",
    r"^generated\s+by", r"^produced\s+by", r"^converted\s+by",
    r"^calibre", r"^sigil", r"^abbyy", r"^fine\s+reader",
]

_JUNK_TITLE_RE = [re.compile(p, re.IGNORECASE) for p in _JUNK_TITLE_PATTERNS]

# префиксы и суффиксы, вырезаемые из иначе валидного заголовка
_STRIP_PATTERNS = [
    (r"^скачать\s+", ""),
    (r"^\s*прочитать\s+(онлайн\s+)?", ""),
    (r"^\s*download\s+", ""),
    (r"^epdf\.pub\s*", ""),
    (r"^\s*pdf\s*drive\s*", ""),
    (r"\s*\(?z-library\)?\s*$", ""),
    (r"\s*ru?lit\.?me\.?\s*$", ""),
    (r"\s*-\s*google\s+документы\s*$", ""),
    (r"\s*-\s*google\s+docs\s*$", ""),
    (r"^microsoft\s+word\s*[-–—:]\s*", ""),
    (r"^microsoft\s+powerpoint\s*[-–—:]\s*", ""),
    (r"^microsoft\s+excel\s*[-–—:]\s*", ""),
    (r"\.indd$", ""), (r"\.docx?$", ""), (r"\.rtf$", ""), (r"\.pdf$", ""),
    (r"\.epub$", ""), (r"\.fb2$", ""), (r"\.djvu$", ""), (r"\.mobi$", ""),
    (r"\s*\(.*?z-?library.*?\)\s*$", ""),
    (r"\s*\[\s*z-?library\s*\]\s*$", ""),
    (r"\s*\(z-lib\.org\)\s*$", ""),
    (r"\s*\(\s*cyberextreme\d*\s+eng\s*\)\s*", " "),
    (r"\s*\(\s*ru\s*\)\s*$", ""),
    (r"\s*@[a-z0-9_.а-яё-]+\s*$", ""),        # водяной знак: «@bookinier»
    (r"\s*[®™©]\s*", " "),                     # охрана товарного знака
    (r"\s*[-–—:]\s*(спб|м|москва|санкт-петербург|минск|киев|ленинград)\.?\s*$", ""),
    (r"\.\d{4,}$", ""),                          # хвостовой id: «.613235»
]

_STRIP_RE = [(re.compile(p, re.IGNORECASE), r) for p, r in _STRIP_PATTERNS]

# имитация имени человека — не заголовок
_AUTHOR_LINE_RE = re.compile(
    r"""^\s*
        (by\b|author:|автор[:\s]|перевод\b|под\s+ред|редактор|
         ред\.|составитель|edited\s+by|translated\s+by|
         [А-ЯЁA-Z][а-яёa-z]+\s+[А-ЯЁA-Z]\.\s*[А-ЯЁA-Z]\.   # Фамилия И. О.
        )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# издательства и типографские строки
_PUBLISHER_LINE_RE = re.compile(
    r"""(
            издательств\w*|типографи\w*|печатно-издательск\w*|
            kindle\s+direct\s+publishing|create\s?space|
            independently\s+published|amazon\s+(com|kindle)|
            lulu\.com|smashwords|bookmate|litres|manning
        )""",
    re.IGNORECASE | re.VERBOSE,
)

# строка серии/выпуска: «НОВАЯ СЕРИЯ», «ВЫПУСК 18» — не название книги
_SERIES_LINE_RE = re.compile(
    r"^\s*[«\"'`]*((новая|старая)\s+)?(серия|series|выпуск|issue|том|volume|"
    r"part|глава|chapter)\b",
    re.IGNORECASE,
)

# слова-метки: не склеиваются с названием
_LABEL_WORD_RE = re.compile(
    r"\b(серия|серии|выпуск|выпуске|том|томе|issue|volume|vol\.|part|number|"
    r"number|№|глава|chapter|издание|edition)\b",
    re.IGNORECASE,
)

# колонтитулы печати из браузера: «1 of 4», «2 14 26, 7 47 PM»
_PRINT_HEADER_RE = re.compile(
    r"^\s*(\d+\s+of\s+\d+|\d{1,2}:\d{2}\s*(am|pm)|"
    r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})"
    r"|\b\d{1,2}:\d{2}\s*(am|pm)\s*$",
    re.IGNORECASE,
)

# строки-заголовки разделов: не название книги
_HEADING_LINE_RE = re.compile(
    r"""^\s*(
            table\s+of\s+contents|contents|preface|foreword|introduction|
            acknowledg(e)?ments|about\s+the\s+author|bibliography|glossary|
            appendix|index|copyright|all\s+rights\s+reserved|
            предисловие|введение|послесловие|оглавление|содержание|
            указатель|библиография|глоссарий|об\s+авторе|приложение
        )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

# короткая аббревиатура кириллицей («МЦНМО») — не название книги
_SHORT_ACRONYM_RE = re.compile(r"^\s*[«\"']?[А-ЯЁ]{2,8}[»\"']?\s*$")

# строки «города издательства»: «Москва · Санкт-Петербург», «BIRMINGHAM - MUMBAI»
_CITIES = frozenset("""
москва санкт-петербург петербург ленинград новосибирск екатеринбург казань
нижний новгород самара омск челябинск ростов-на-дону уфа красноярск пермь
воронеж волгоград минск киев харьков одесса днепр лодзь варшава краков
прага софия рига вильнюс таллин лондон париж берлин мадрид рим милан турин
амстердам брюссель вена стокгольм осло копенгаген хельсинки бостон нью-йорк
чикаго сан-франциско сиэтл индианаполис westford birmingham mumbai bombay
delhi new delhi new york london paris berlin madrid rome milan amsterdam
brussels vienna prague warsaw tokyo beijing shanghai singapore toronto
sydney melbourne auckland dublin edinburgh glasgow manchester cambridge
oxford heidelberg munich hamburg cologne geneva zurich lisbon athens
budapest bucharest belgrade zagreb kiev minsk moscow petersburg
farnham sebastopol colophon
boston chicago seattle philadelphia pittsburgh houston denver portland
austin atlanta dallas detroit nashville hoboken raleigh
san francisco st petersburg saint petersburg
""".split())

_CITY_SPLIT_RE = re.compile(r"\s+[-–—]\s+|[·,;|]|\s+и\s+|\s+and\s+", re.IGNORECASE)


def is_city_line(text: str) -> bool:
    """Строка целиком состоит из названий городов (список городов издания)."""
    t = text.strip().strip("«»\"'.,")
    t = re.sub(r"\b(19|20)\d{2}\b", "", t).strip()   # «Москва, 2014»
    chunks = _CITY_SPLIT_RE.split(t)
    words = [w.strip(" .").lower() for chunk in chunks for w in chunk.split()]
    words = [w for w in words if w]
    if not words:
        return False
    i = 0
    while i < len(words):
        if i + 1 < len(words) and f"{words[i]} {words[i + 1]}" in _CITIES:
            i += 2                                  # «New York»
        elif words[i] in _CITIES:
            i += 1
        else:
            return False
    return True

# служебные строки, которые точно не заголовок
_SERVICE_LINE_RE = re.compile(
    r"""(©|\bISBN\b|\bISSN\b|\bУДК\b|\bББК\b|https?://|www\.|@[a-z0-9.-]+|
         ^\s*стр\.?\s*\d|^\s*page\s+\d+|^\s*\d+\s*/\s*\d+\s*$|^\s*[ivxlc]+\s*$)""",
    re.IGNORECASE | re.VERBOSE,
)


def is_junk_title(text: str) -> bool:
    """Похоже ли строку на служебный/мусорный «заголовок»."""
    t = text.strip()
    if not t:
        return True
    if is_city_line(t):
        return True
    if _SERIES_LINE_RE.match(t):
        return True
    if _HEADING_LINE_RE.match(t):
        return True
    # строка, разбитая на однобуквенные слова: «И З Д А Т Е Л Ь С Т В О»
    # (инициалы в именах «Дэвис К. А., Фортунато…» — не мусор)
    words = t.split()
    singles = sum(1 for w in words if len(w.strip(".,;:")) == 1)
    if singles >= 3 and singles / len(words) > 0.5:
        return True
    # издательство — только как короткая строка-подпись (не название книги)
    if _PUBLISHER_LINE_RE.search(t) and len(t) <= 100:
        return True
    return any(rx.search(t) for rx in _JUNK_TITLE_RE) or bool(
        _PRINT_HEADER_RE.match(t) or _SHORT_ACRONYM_RE.match(t)
    )


def clean_title(text: str) -> str:
    """Вычистить служебные префиксы/суффиксы из заголовка."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\u00a0", " ").replace("_", " ")
    for _ in range(2):                      # повтор на случай «Скачать ... (Z-Library)»
        for rx, repl in _STRIP_RE:
            t = rx.sub(repl, t)
    t = re.sub(r"\s+", " ", t).strip(" \t-–—·•|:;,.")
    return t


def is_author_line(text: str) -> bool:
    """Строка больше похожа на имя автора/редактора, чем на заголовок."""
    return bool(_AUTHOR_LINE_RE.match(text.strip()))


def is_service_line(text: str) -> bool:
    """Служебная строка (ISBN, колонтитул, ссылка) — не заголовок."""
    return bool(_SERVICE_LINE_RE.search(text))


def is_label_line(text: str) -> bool:
    """Строка-метка («НОВАЯ СЕРИЯ», «ВЫПУСК 18») — не часть названия."""
    return bool(_LABEL_WORD_RE.search(text))


# ---------------------------------------------------------------------------
# Качество извлечённого текста (детект кракозябр)
# ---------------------------------------------------------------------------

# диапазоны, в которых «живёт» мусор от нестандартной кодировки шрифтов
_GARBAGE_RANGES = (
    (0x0080, 0x009F),   # C1-управляющие
    (0x00A0, 0x00BF),   # знаки пунктуации Latin-1 (£¤¦§©«» и т. п.)
    (0x0250, 0x02FF),   # расширения МФА
    (0x0300, 0x036F),   # комбинируемые диакритики без базовых символов
    (0x2000, 0x206F),   # служебная пунктуация (в умеренных долях)
    (0x2190, 0x2BFF),   # стрелки, математические символы, рамки
    (0xFFFD, 0xFFFD),   # символ замены
)


def _in_garbage_range(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _GARBAGE_RANGES)


def strip_special(text: str) -> str:
    """Оставить только буквы, цифры и пробелы; пробелы схлопнуть.

    Используется в режиме «название из всего текста» (--title-from-text):
    весь текст страницы без спецсимволов склеивается в одно название.
    """
    cleaned = re.sub(r"[^\w\s]", " ", text or "", flags=re.UNICODE)
    cleaned = re.sub(r"_", " ", cleaned)          # подчёркивания — тоже мусор
    return re.sub(r"\s+", " ", cleaned).strip()


def text_quality(text: str) -> TextQuality:
    """Оценить, пригоден ли извлечённый текст для поиска заголовка."""
    chars = [c for c in (text or "") if not c.isspace()]
    if not chars:
        return TextQuality.EMPTY

    letters = sum(1 for c in chars if unicodedata.category(c).startswith("L"))
    garbage = sum(1 for c in chars if _in_garbage_range(c))
    replacement = sum(1 for c in chars if c == "\ufffd")

    n = len(chars)
    if replacement / n > 0.05 or garbage / n > 0.12 or letters / n < 0.55:
        return TextQuality.GARBAGE

    # раздробленный текст: «W ICKED COOL», «SHELL SCRIP T S» — обработан
    # нестандартной кодировкой шрифтов, слова разбиты посреди букв.
    # смотрим на НАЧАЛО текста (титульную страницу), где ищется название
    head_tokens = [w.strip(".,;:!?()«»\"'…-–—") for w in text[:1000].split()]
    head_tokens = [w for w in head_tokens if w]
    if len(head_tokens) >= 5:
        short = sum(1 for w in head_tokens if len(w) <= 2)
        if short / len(head_tokens) > 0.5:
            return TextQuality.GARBAGE
    return TextQuality.GOOD


# ---------------------------------------------------------------------------
# Имя автора
# ---------------------------------------------------------------------------

_JUNK_AUTHOR_RE = re.compile(
    r"""^(
            \.|-|test|user|admin(istrator)?|unknown|none|null|
            microsoft|adobe|abbyy|calibre|sigil|kindle|amazon|
            author|автор|имя\s+пользователя|
            сборник|коллектив|авторский\s+коллектив|редколлегия|
            редакционная\s+коллегия|разные\s+авторы|various\s+authors|
            anonymous|anonym|
            \d+|[a-zа-яё]\b
        )
        $""",
    re.IGNORECASE | re.VERBOSE,
)

# служебные слова: строка с ними — не имя («And Unix Systems» из OCR)
_SOFT_NOT_NAME_RE = re.compile(
    r"^(and|or|the|of|for|with|an|a|и|в|на|с|к|у|о|для)$", re.IGNORECASE,
)
_STRONG_NOT_NAME_RE = re.compile(
    r"""^(systems?|solutions?|press|publishing|books?|media|group|
          company|inc|ltd|llc|unix|linux|windows|edition|series|
          volume|chapter|издание|серия|том|глава|aspose|epubtopdfconverter)$""",
    re.IGNORECASE | re.VERBOSE,
)


def clean_author(text: str) -> str:
    """Нормализовать имя автора; вернуть "" для служебных значений."""
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\u00a0", " ").replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip(" \t-–—,;")
    t = re.sub(r"\s*\(\s*z-?library\s*\)\s*$", "", t, flags=re.IGNORECASE)
    if not t or _JUNK_AUTHOR_RE.match(t):
        return ""
    words = [w.strip(",'’") for w in t.split()]
    parts = [p for p in re.split(r"[\s.]+", t) if p]
    first = words[0].strip(",'’")
    # инициал («О.») — не предлог: стоп-лист смотрит на полные слова
    if not first.endswith(".") and _SOFT_NOT_NAME_RE.match(first.strip(".,'’")):
        return ""
    if any(_STRONG_NOT_NAME_RE.match(p) for p in parts):
        return ""
    if len(t) > 60 or len(t.split()) > 6 or sum(c.isdigit() for c in t) > 2:
        return ""
    if any(_in_garbage_range(c) for c in t):
        return ""
    # имя должно начинаться с заглавной буквы или содержать инициалы
    if not re.search(r"[А-ЯЁA-Z]", t):
        return ""
    # «АРТУР ДУМЧЕВ» → «Артур Думчев»
    if t.isupper() and len(t.split()) in (2, 3):
        t = " ".join(w.capitalize() for w in t.split())
    return t
