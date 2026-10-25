"""Тесты текстового слоя DjVu и рендеринга страниц (djvulibre)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from titlemark.extractors.djvu import djvulibre_text, find_annotations
from titlemark.ocr import render_page
from titlemark.renamer import plan_rename

from test_extractors import make_djvu


class TestDjvuText(unittest.TestCase):
    def test_pages_split_and_truncated(self):
        pages = "первая страница\fвторая страница\fтретья страница"
        with mock.patch("titlemark.extractors.djvu._run", return_value=pages), \
             mock.patch("titlemark.extractors.djvu.find_tool",
                        return_value="/usr/bin/djvutxt"):
            text = djvulibre_text(Path("scan.djvu"), max_pages=2)
        self.assertIn("первая страница", text)
        self.assertIn("вторая страница", text)
        self.assertNotIn("третья", text)

    def test_no_djvulibre_tools(self):
        with mock.patch("titlemark.extractors.djvu.find_tool",
                        return_value=None):
            self.assertEqual(djvulibre_text(Path("scan.djvu")), "")

    def test_empty_output(self):
        with mock.patch("titlemark.extractors.djvu._run", return_value=""), \
             mock.patch("titlemark.extractors.djvu.find_tool",
                        return_value="/usr/bin/djvutxt"):
            self.assertEqual(djvulibre_text(Path("scan.djvu")), "")


class TestDjvuPlan(unittest.TestCase):
    def test_text_layer_used_for_title(self):
        """DjVu без аннотаций, но с текстовым слоем (TXTz) получает название."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "013cf8222b4d0961ca03f0a5fcedc488"
            p.write_bytes(make_djvu("", ""))                  # аннотаций нет
            with mock.patch(
                    "titlemark.extractors.djvu.djvulibre_text",
                    return_value="Кибернетический сборник\nНОВАЯ СЕРИЯ\n"
                                 "ИЗДАТЕЛЬСТВО «МИР»\nМОСКВА 1981"):
                plan = plan_rename(p, use_ocr=False)
            self.assertEqual(plan.status, "ok")
            self.assertIn("Кибернетический", plan.new_name)
            self.assertNotIn("ИЗДАТЕЛЬСТВО", plan.new_name)   # издатель — мусор


class TestOcrRendering(unittest.TestCase):
    def test_djvu_rendered_with_ddjvu(self):
        calls = []

        def fake_run(cmd, timeout):
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b"image")     # ddjvu пишет файл в последний арг
            return ""

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("titlemark.ocr.find_tool",
                            return_value="/usr/bin/ddjvu"), \
                 mock.patch("titlemark.ocr._run", side_effect=fake_run):
                img = render_page(Path("scan.djvu"), 1, Path(tmp))
        self.assertIsNotNone(img)
        self.assertTrue(calls[0][0].endswith("ddjvu"))
        self.assertEqual(calls[0][1], "-page=1")
        self.assertIn("-format=tiff", calls[0])

    def test_pdf_rendered_with_pdftoppm(self):
        calls = []

        def fake_run(cmd, timeout):
            calls.append(cmd)
            Path(cmd[-1]).with_suffix(".png").write_bytes(b"image")
            return ""

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("titlemark.ocr.find_tool",
                            return_value="/usr/bin/pdftoppm"), \
                 mock.patch("titlemark.ocr._run", side_effect=fake_run):
                img = render_page(Path("book.pdf"), 1, Path(tmp))
        self.assertIsNotNone(img)
        self.assertTrue(calls[0][0].endswith("pdftoppm"))


class TestDjvuAnnotationsStillWork(unittest.TestCase):
    def test_annotations(self):
        found = find_annotations(make_djvu("Altium Designer", "Сабунин А. Е."))
        self.assertEqual(found["title"], "Altium Designer")
        self.assertEqual(found["author"], "Сабунин А. Е.")


if __name__ == "__main__":
    unittest.main()
