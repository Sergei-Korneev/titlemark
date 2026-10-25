"""Тесты определения формата по сигнатуре (файлы без расширения)."""

import tempfile
import unittest
from pathlib import Path

from shelfmark.renamer import iter_document_files, plan_rename
from shelfmark.signature import detect_extension

from test_extractors import make_djvu, make_docx, make_epub, make_fb2, make_mobi


class TestDetectExtension(unittest.TestCase):
    def _detect(self, data: bytes) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "00acaf02b9dfa6495f4842bd5de2a675"
            p.write_bytes(data)
            return detect_extension(p)

    def test_pdf(self):
        self.assertEqual(self._detect(b"%PDF-1.5\n1 0 obj\n"), ".pdf")

    def test_djvu(self):
        self.assertEqual(self._detect(make_djvu("Титул", "Автор")), ".djvu")

    def test_mobi(self):
        self.assertEqual(self._detect(make_mobi()), ".mobi")

    def test_epub(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_epub(Path(tmp) / "hash-name", "Title", "Author", "2020-01-01")
            self.assertEqual(detect_extension(p), ".epub")

    def test_docx(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_docx(Path(tmp) / "hash-name", "Title", "Author")
            self.assertEqual(detect_extension(p), ".docx")

    def test_fb2(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_fb2(Path(tmp) / "hash-name", "Заголовок", "Имя", "Фамилия")
            self.assertEqual(detect_extension(p), ".fb2")

    def test_unknown(self):
        self.assertEqual(self._detect(b"\x00\x01\x02\x03unknown garbage"), "")

    def test_png_skipped(self):
        self.assertEqual(self._detect(b"\x89PNG\r\n\x1a\n\x00\x00"), "")

    def test_empty_file(self):
        self.assertEqual(self._detect(b""), "")

    def test_wrong_extension_still_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "photo.jpg"
            p.write_bytes(b"%PDF-1.4 fake")
            self.assertEqual(detect_extension(p), ".pdf")


class TestRenameWithoutExtension(unittest.TestCase):
    def test_epub_hash_name_gets_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_epub(Path(tmp) / "00acaf02b9dfa6495f4842bd5de2a675",
                          "It Ends With Us", "Colleen Hoover", "2020-05-01")
            plan = plan_rename(p, use_ocr=False)
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.new_name,
                             "Colleen Hoover - It Ends With Us [2020].epub")

    def test_djvu_hash_name_gets_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "00c1dbfd61f7a0252de228c415f2ae9c"
            p.write_bytes(make_djvu("Altium Designer", "Сабунин А. Е."))
            plan = plan_rename(p, use_ocr=False)
            self.assertEqual(plan.new_name, "Сабунин А. Е. - Altium Designer.djvu")

    def test_mobi_hash_name_gets_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "abcdef0123456789"
            p.write_bytes(make_mobi(title=b"Full Book Name", author=b"Ivanov Ivan"))
            plan = plan_rename(p, use_ocr=False)
            self.assertEqual(plan.new_name, "Ivanov Ivan - Full Book Name.mobi")

    def test_directory_scan_includes_hash_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_epub(root / "00acaf02b9dfa6495f4842bd5de2a675",
                      "Title", "Author", "2020-01-01")
            (root / "notes.txt").write_text("текст")
            (root / "7z-archive").write_bytes(b"7z\xbc\xaf\x27\x1c\x00data")
            files = iter_document_files([root])
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, "00acaf02b9dfa6495f4842bd5de2a675")

    def test_named_files_still_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = make_epub(Path(tmp) / "book.epub",
                          "Learning Git", "Anna Skoulikari", "2020-01-01")
            plan = plan_rename(p, use_ocr=False)
            self.assertEqual(plan.new_name, "Anna Skoulikari - Learning Git [2020].epub")


if __name__ == "__main__":
    unittest.main()
