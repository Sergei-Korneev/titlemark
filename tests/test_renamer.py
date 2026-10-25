"""Тесты запасного разбора имени файла и правил замены названия."""

import tempfile
import unittest
from pathlib import Path

from shelfmark.renamer import (
    _fb_richer,
    _similar_title,
    _title_from_filename,
    _weak_title,
    plan_rename,
)
from test_extractors import make_epub


class TestTitleFromFilename(unittest.TestCase):
    def test_numbered_prefix_kept_when_part_of_title(self):
        title, author = _title_from_filename(Path("40_алгоритмов_Python.pdf"))
        self.assertEqual(title, "40 алгоритмов Python")
        self.assertEqual(author, "")

    def test_numbered_prefix_stripped(self):
        title, author = _title_from_filename(Path("03_IT_ENDS_WITH_US_by_Colleen_Hoover.epub"))
        self.assertEqual(title, "IT ENDS WITH US")
        self.assertEqual(author, "Colleen Hoover")

    def test_author_dash_title(self):
        title, author = _title_from_filename(
            Path("Elizabeth Ricker - Brain An Owner's Guide.epub"))
        self.assertEqual(title, "Brain An Owner's Guide")
        self.assertEqual(author, "Elizabeth Ricker")

    def test_author_dash_title_hyphenated_surname(self):
        title, author = _title_from_filename(
            Path("Марк Бруцкий-Стемпковский - PytnGlazHakera [2022].pdf"))
        self.assertEqual(title, "PytnGlazHakera [2022]")
        self.assertEqual(author, "Марк Бруцкий-Стемпковский")

    def test_paren_author_stripped(self):
        title, author = _title_from_filename(Path("Tampa (Alissa Nutting) (Z-Library).epub"))
        self.assertEqual(title, "Tampa")
        self.assertEqual(author, "")

    def test_paren_subtitle_kept(self):
        title, _ = _title_from_filename(Path("Clean Code (2nd Edition).epub"))
        self.assertIn("2nd Edition", title)

    def test_trailing_author_stripped(self):
        title, author = _title_from_filename(
            Path("Rethink_Your_Position_-_Katy_Bowman.epub"))
        self.assertEqual(title, "Rethink Your Position")
        self.assertEqual(author, "Katy Bowman")

    def test_trailing_surname_stripped(self):
        title, author = _title_from_filename(
            Path("Путеводитель по базам данных - Комаров - Владимир Комаров.pdf"))
        self.assertEqual(title, "Путеводитель по базам данных")
        self.assertEqual(author, "Владимир Комаров")

    def test_edition_suffix_not_author(self):
        title, author = _title_from_filename(Path("Clean Code - Second Edition.epub"))
        self.assertEqual(title, "Clean Code - Second Edition")
        self.assertEqual(author, "")


class TestTitleQualityRules(unittest.TestCase):
    def test_weak(self):
        self.assertTrue(_weak_title("на Python"))
        self.assertTrue(_weak_title("М. МЦНМО, 2016"))
        self.assertTrue(_weak_title(""))
        self.assertFalse(_weak_title("Современная английская грамматика"))
        self.assertFalse(_weak_title("40 алгоритмов Python"))

    def test_fb_richer(self):
        self.assertTrue(_fb_richer("Brain An Owner's Guide", "Brain"))
        self.assertTrue(_fb_richer("Весь Linux. Для тех", "ВЕСЬ"))
        self.assertFalse(_fb_richer("Matrix Coding Library",
                                    "Linux Command Line and Shell Scripting BIBLE"))
        self.assertFalse(_fb_richer("Brain", "Brain"))

    def test_similar(self):
        self.assertTrue(_similar_title(
            "Весь Linux. Для тех, кто хочет стать профессионалом",
            "ВЕСЬ LINUX. Для ТЕХ, КТО ХОЧЕТ СГАТЬ ПРОФЕССИОНАЛОМ"))
        self.assertFalse(_similar_title("Docker Deep Dive", "Нейрофитнес"))


class TestAuthorTitleDedup(unittest.TestCase):
    def test_title_equals_author_falls_back_to_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            name = "Прикладное машинное обучение без учителя.epub"
            path = make_epub(Path(tmp) / name, "Ан кур Пател", "Анкур Пател", "2023-01-01")
            plan = plan_rename(path, use_ocr=False)
            self.assertEqual(
                plan.new_name,
                "Анкур Пател - Прикладное машинное обучение без учителя [2023].epub")


if __name__ == "__main__":
    unittest.main()
