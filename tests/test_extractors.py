"""Тесты экстракторов на синтетических файлах + интеграционный тест переименования."""

import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from shelfmark.extractors.djvu import find_annotations
from shelfmark.extractors.mobi import parse_mobi
from shelfmark.extractors import get_extractor
from shelfmark.models import Source
from shelfmark.renamer import apply_plans, plan_rename

# ---------------------------------------------------------------------------
# строители синтетических файлов
# ---------------------------------------------------------------------------


def make_epub(path: Path, title: str, creator: str, date: str = "") -> Path:
    opf = f"""<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>{title}</dc:title>
        <dc:creator>{creator}</dc:creator>
        <dc:date>{date}</dc:date>
      </metadata>
    </package>"""
    container = """<?xml version="1.0"?>
    <container version="1.0">
      <rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>
    </container>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch1.xhtml", "<html><body>text</body></html>")
    return path


def make_fb2(path: Path, title: str, first: str, last: str, year: str = "",
             middle: str = "") -> Path:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
    <FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
      <description>
        <title-info>
          <author><first-name>{first}</first-name><middle-name>{middle}</middle-name><last-name>{last}</last-name></author>
          <book-title>{title}</book-title>
          <date><year>{year}</year></date>
        </title-info>
      </description>
      <body><section><p>текст</p></section></body>
    </FictionBook>"""
    path.write_text(xml, encoding="utf-8")
    return path


def make_mobi(title: bytes = b"Full Book Name", author: bytes = b"Ivanov Ivan",
              updated_title: bytes = b"") -> bytes:
    """Минимальный валидный MOBI: PDB + PalmDOC + MOBI + EXTH."""
    mobi_header_len = 0xE8
    exth_off = 0x10 + mobi_header_len

    records = b""
    count = 0
    for rtype, value in ((503, updated_title), (100, author)):
        if not value:
            continue
        records += struct.pack(">II", rtype, 8 + len(value)) + value
        count += 1
    exth = b"EXTH" + struct.pack(">II", 12 + len(records), count) + records

    rec0 = bytearray(exth_off + len(exth) + 256)
    struct.pack_into(">H", rec0, 0x00, 1)         # compression
    struct.pack_into(">I", rec0, 0x04, 100)       # text length
    struct.pack_into(">H", rec0, 0x08, 1)         # record count
    struct.pack_into(">H", rec0, 0x0A, 4096)      # record size
    rec0[0x10:0x14] = b"MOBI"
    struct.pack_into(">I", rec0, 0x14, mobi_header_len)
    struct.pack_into(">I", rec0, 0x18, 2)         # mobi type
    struct.pack_into(">I", rec0, 0x1C, 65001)     # encoding: utf-8
    struct.pack_into(">I", rec0, 0x80, 0x40)      # EXTH present
    rec0[exth_off:exth_off + len(exth)] = exth

    fullname_off = exth_off + len(exth)
    rec0[fullname_off:fullname_off + len(title)] = title
    struct.pack_into(">I", rec0, 0x54, fullname_off)
    struct.pack_into(">I", rec0, 0x58, len(title))

    pdb = bytearray(0x56)
    pdb[0:8] = b"TestBook"
    pdb[60:68] = b"BOOKMOBI"                   # тип/создатель PalmDB
    struct.pack_into(">H", pdb, 0x4C, 1)          # numRecords
    struct.pack_into(">I", pdb, 0x4E, 0x56)       # offset record 0
    return bytes(pdb) + bytes(rec0)


def _iff_chunk(cid: bytes, body: bytes) -> bytes:
    pad = b"\x00" if len(body) % 2 else b""
    return cid + struct.pack(">I", len(body)) + body + pad


def make_djvu(title: str, author: str) -> bytes:
    ann = f'(metadata\n (title "{title}")\n (author "{author}"))'.encode("utf-8")
    inner = _iff_chunk(b"ANTa", ann)
    form_body = b"DJVU" + inner
    return b"AT&T" + b"FORM" + struct.pack(">I", len(form_body)) + form_body


def make_docx(path: Path, title: str, creator: str, text: str = "") -> Path:
    core = f"""<?xml version="1.0"?>
    <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
      xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:title>{title}</dc:title>
      <dc:creator>{creator}</dc:creator>
      <dcterms:created xmlns:dcterms="http://purl.org/dc/terms/">2021-05-01T00:00:00Z</dcterms:created>
    </cp:coreProperties>"""
    document = (
        '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text or title}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("docProps/core.xml", core)
        zf.writestr("word/document.xml", document)
    return path


# ---------------------------------------------------------------------------
# тесты
# ---------------------------------------------------------------------------


class TestMobi(unittest.TestCase):
    def test_full_name_fallback(self):
        title, author, year = parse_mobi(make_mobi())
        self.assertEqual(title, "Full Book Name")
        self.assertEqual(author, "Ivanov Ivan")
        self.assertEqual(year, "")

    def test_updated_title_wins(self):
        title, author, _ = parse_mobi(make_mobi(updated_title=b"New Title"))
        self.assertEqual(title, "New Title")
        self.assertEqual(author, "Ivanov Ivan")

    def test_garbage(self):
        self.assertEqual(parse_mobi(b"not a mobi file at all"), ("", "", ""))


class TestDjvu(unittest.TestCase):
    def test_annotations(self):
        found = find_annotations(make_djvu("Теоретическая фонетика", "Ситель В. В."))
        self.assertEqual(found["title"], "Теоретическая фонетика")
        self.assertEqual(found["author"], "Ситель В. В.")

    def test_no_annotations(self):
        self.assertEqual(find_annotations(b"AT&TFORM\x00\x00\x00\x04DJVU"), {})


class TestExtractorsByExtension(unittest.TestCase):
    def test_registry(self):
        for name in ("a.pdf", "a.epub", "a.fb2", "a.mobi", "a.djvu", "a.docx"):
            self.assertIsNotNone(get_extractor(Path(name)), name)
        self.assertIsNone(get_extractor(Path("a.zip")))


class TestExtract(unittest.TestCase):
    def test_epub_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_epub(Path(tmp) / "bad_name.epub",
                             "It Ends With Us", "Colleen Hoover", "2020-05-01")
            info = get_extractor(path).extract(path, use_ocr=False)
            self.assertEqual(info.title, "It Ends With Us")
            self.assertEqual(info.author, "Colleen Hoover")
            self.assertEqual(info.year, "2020")
            self.assertIs(info.title_source, Source.METADATA)

    def test_fb2_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_fb2(Path(tmp) / "345852.fb2",
                            "Мой домашний справочник", "Виктор", "Пелевин", "1999")
            info = get_extractor(path).extract(path, use_ocr=False)
            self.assertEqual(info.title, "Мой домашний справочник")
            self.assertEqual(info.author, "Виктор Пелевин")
            self.assertEqual(info.year, "1999")

    def test_fb2_initials_author(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_fb2(Path(tmp) / "345852.fb2",
                            "Карманный справочник туриста", "Ю", "Штюрмер",
                            "2010", middle="А")
            info = get_extractor(path).extract(path, use_ocr=False)
            self.assertEqual(info.author, "Штюрмер Ю. А.")

    def test_docx_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_docx(Path(tmp) / "report.docx",
                             "Отчёт по аудиту", "Иванов Иван")
            info = get_extractor(path).extract(path, use_ocr=False)
            self.assertEqual(info.title, "Отчёт по аудиту")
            self.assertEqual(info.author, "Иванов Иван")
            self.assertEqual(info.year, "2021")

    def test_djvu_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Altium.djvu"
            path.write_bytes(make_djvu("Altium Designer", "Сабунин А. Е."))
            info = get_extractor(path).extract(path, use_ocr=False)
            self.assertEqual(info.title, "Altium Designer")
            self.assertEqual(info.author, "Сабунин А. Е.")


class TestPlanAndApply(unittest.TestCase):
    def test_plan_epub(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_epub(Path(tmp) / "03_IT_ENDS_WITH_US.epub",
                             "It Ends With Us", "Colleen Hoover", "2020-05-01")
            plan = plan_rename(path, use_ocr=False)
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.new_name,
                             "Colleen Hoover - It Ends With Us [2020].epub")

    def test_apply_renames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_epub(Path(tmp) / "book.epub",
                             "It Ends With Us", "Colleen Hoover", "2020-05-01")
            plans = [plan_rename(path, use_ocr=False)]
            apply_plans(plans)
            self.assertFalse(path.exists())
            self.assertTrue((Path(tmp) / "Colleen Hoover - It Ends With Us [2020].epub").exists())

    def test_filename_richer_title(self):
        # метаданные дали обрывок («Brain»), имя файла полнее
        with tempfile.TemporaryDirectory() as tmp:
            path = make_epub(
                Path(tmp) / "Elizabeth Ricker - Brain An Owner's Guide.epub",
                "Brain", "Elizabeth R. Ricker", "2020-01-01")
            plan = plan_rename(path, use_ocr=False)
            self.assertEqual(plan.new_name,
                             "Elizabeth R. Ricker - Brain An Owner's Guide [2020].epub")

    def test_filename_not_richer_keeps_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = make_epub(Path(tmp) / "Matrix _ Coding Library.epub",
                             "Linux Command Line and Shell Scripting Bible",
                             "Richard Blum", "2022-01-01")
            plan = plan_rename(path, use_ocr=False)
            self.assertEqual(
                plan.new_name,
                "Richard Blum - Linux Command Line and Shell Scripting Bible [2022].epub")

    def test_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.zip"
            path.write_bytes(b"PK")
            plan = plan_rename(path, use_ocr=False)
            self.assertEqual(plan.status, "unsupported")

    def test_no_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "29623753.pdf"       # PDF-заголовка нет, имя-номер
            path.write_bytes(b"%PDF-1.4 stub")
            plan = plan_rename(path, use_ocr=False)
            self.assertEqual(plan.status, "no-title")


if __name__ == "__main__":
    unittest.main()
