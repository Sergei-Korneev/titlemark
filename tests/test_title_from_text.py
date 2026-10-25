"""Тесты режима --title-from-text: название из всего текста страницы."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shelfmark.extractors.base import Extractor
from shelfmark.models import Source
from shelfmark.renamer import plan_rename
from shelfmark.textclean import strip_special
from shelfmark.titlefinder import full_text_title

PAGE_TEXT = """
                        АРТУР ДУМЧЕВ

                        ПОМНИТЬ ВСЕ
                   ПРАКТИЧЕСКОЕ РУКОВОДСТВО
                     ПО РАЗВИТИЮ ПАМЯТИ

          Издательство «Манн, Иванов и Фербер»
                        Москва, 2014
                        УДК 811.953
                  ISBN 978-5-00057-015-9
"""


class TestStripSpecial(unittest.TestCase):
    def test_keeps_letters_and_digits(self):
        self.assertEqual(strip_special("«ПОМНИТЬ ВСЕ!» — №1_test"),
                         "ПОМНИТЬ ВСЕ 1 test")

    def test_collapses_spaces(self):
        self.assertEqual(strip_special("  много\n\tпробелов  "), "много пробелов")


class TestFullTextTitle(unittest.TestCase):
    def test_fragments_joined_junk_dropped(self):
        title = full_text_title(PAGE_TEXT, exclude_author="Артур Думчев")
        self.assertEqual(
            title,
            "ПОМНИТЬ ВСЕ ПРАКТИЧЕСКОЕ РУКОВОДСТВО ПО РАЗВИТИЮ ПАМЯТИ")

    def test_author_and_service_lines_dropped(self):
        title = full_text_title(PAGE_TEXT, exclude_author="Артур Думчев")
        for junk in ("АРТУР ДУМЧЕВ", "Издательство", "Москва", "УДК", "ISBN"):
            self.assertNotIn(junk, title)

    def test_empty_text(self):
        self.assertEqual(full_text_title("   \n  "), "")

    def test_person_title_kept_when_not_author(self):
        text = "АННА КАРЕНИНА\nЛЕВ ТОЛСТОЙ\nРоман"
        title = full_text_title(text, exclude_author="Лев Толстой")
        self.assertIn("АННА КАРЕНИНА", title)


class _StubExtractor(Extractor):
    extensions = (".stub",)

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        return "", "", ""

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        return PAGE_TEXT


class TestExtractTitleFromText(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "29623753.stub"
        self.path.write_bytes(b"stub")

    def test_full_text_mode(self):
        info = _StubExtractor().extract(self.path, use_ocr=False,
                                        title_from_full_text=1)
        self.assertEqual(
            info.title,
            "ПОМНИТЬ ВСЕ ПРАКТИЧЕСКОЕ РУКОВОДСТВО ПО РАЗВИТИЮ ПАМЯТИ")
        self.assertTrue(any("--title-from-text" in w for w in info.warnings))

    def test_off_by_default(self):
        info = _StubExtractor().extract(self.path, use_ocr=False)
        self.assertEqual(
            info.title,
            "ПОМНИТЬ ВСЕ ПРАКТИЧЕСКОЕ РУКОВОДСТВО ПО РАЗВИТИЮ ПАМЯТИ")
        self.assertFalse(any("--title-from-text" in w for w in info.warnings))


class TestPlanRenamePlumbing(unittest.TestCase):
    def test_plan_rename_with_title_from_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "00acaf02b9dfa6495f4842bd5de2a675"
            p.write_bytes(b"%PDF-1.4 stub")
            with mock.patch(
                    "shelfmark.extractors.pdf.PdfExtractor.read_text",
                    return_value=PAGE_TEXT):
                plan = plan_rename(p, use_ocr=False, title_from_text=1)
            self.assertEqual(plan.status, "ok")
            self.assertIn("ПОМНИТЬ ВСЕ ПРАКТИЧЕСКОЕ РУКОВОДСТВО", plan.new_name)
            self.assertTrue(plan.new_name.endswith(".pdf"))

    def test_cli_parses_flag_and_path(self):
        from shelfmark.cli import build_parser

        args = build_parser().parse_args(
            ["--title-from-text", "--title-pages", "2", "книга.pdf"])
        self.assertTrue(args.title_from_text)
        self.assertEqual(args.title_pages, 2)
        self.assertEqual([str(p) for p in args.paths], ["книга.pdf"])

    def test_cli_version(self):
        from shelfmark.cli import build_parser

        with self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_cli_rejects_bad_template(self):
        from shelfmark.cli import main

        code = main(["--naming-template", "{title}-{год}", "книга.pdf"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
