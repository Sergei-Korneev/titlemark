"""Тесты построения имени файла."""

import tempfile
import unittest
from pathlib import Path

from titlemark.naming import (
    build_new_name,
    extract_year_from_name,
    sanitize_component,
    unique_name,
    validate_template,
)


class TestSanitize(unittest.TestCase):
    def test_forbidden_chars(self):
        self.assertEqual(sanitize_component('А/Б: "Тест"*?'), "А Б Тест")

    def test_control_chars(self):
        self.assertEqual(sanitize_component("a\x00b\x1fc"), "a b c")

    def test_spaces(self):
        self.assertEqual(sanitize_component("  много   пробелов  "), "много пробелов")


class TestBuildName(unittest.TestCase):
    def test_author_title_year(self):
        name = build_new_name(Path("old.pdf"), "Название", "Иванов И. И.", "2019")
        self.assertEqual(name, "Иванов И. И. - Название [2019].pdf")

    def test_no_author(self):
        name = build_new_name(Path("old.epub"), "Название", "", "")
        self.assertEqual(name, "Название.epub")

    def test_nothing_found_keeps_name(self):
        self.assertEqual(build_new_name(Path("old.pdf"), "", "", ""), "old.pdf")

    def test_year_not_duplicated(self):
        name = build_new_name(Path("old.pdf"), "ГОСТ 2015", "", "2015")
        self.assertEqual(name, "ГОСТ 2015.pdf")

    def test_extension_case(self):
        name = build_new_name(Path("old.PDF"), "Название", "", "")
        self.assertEqual(name, "Название.pdf")

    def test_truncation_by_bytes(self):
        long_title = "очень длинный заголовок " * 30
        name = build_new_name(Path("old.pdf"), long_title, "Автор", "", max_bytes=120)
        self.assertLessEqual(len(name.encode("utf-8")), 120)
        self.assertTrue(name.endswith(".pdf"))
        self.assertIn("…", name)

    def test_truncation_word_boundary(self):
        name = build_new_name(Path("old.pdf"), "alpha beta gamma delta epsilon",
                             "", "", max_bytes=20)
        self.assertNotIn("alpha beta g…", name)
        self.assertTrue(name.endswith(".pdf"))


class TestUniqueName(unittest.TestCase):
    def test_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Название.pdf").write_bytes(b"x")
            target = root / "Название.pdf"
            self.assertEqual(unique_name(target), "Название (2).pdf")
            (root / "Название (2).pdf").write_bytes(b"x")
            self.assertEqual(unique_name(target), "Название (3).pdf")

    def test_taken_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "new.pdf"
            self.assertEqual(unique_name(target, {"new.pdf"}), "new (2).pdf")

    def test_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "new.pdf"
            self.assertEqual(unique_name(target), "new.pdf")


class TestYearFromName(unittest.TestCase):
    def test_year(self):
        self.assertEqual(extract_year_from_name(Path("book_2019_scan.pdf")), "2019")
        self.assertEqual(extract_year_from_name(Path("29623753.pdf")), "")
        # год внутри названия не дублируется благодаря build_new_name
        self.assertEqual(extract_year_from_name(Path("1984.pdf")), "1984")


class TestNamingTemplate(unittest.TestCase):
    def test_validate_ok(self):
        for tpl in ("{title}", "{title}-{year}", "{author} - {title} [{year}]",
                    "prefix {title} suffix", "{title}"):
            self.assertIsNone(validate_template(tpl), tpl)

    def test_validate_unknown_placeholder(self):
        err = validate_template("{title}-{год}")
        self.assertIn("unknown placeholder", err)
        self.assertIn("год", err)

    def test_validate_broken(self):
        self.assertIn("invalid template", validate_template("{title"))

    def test_custom_template(self):
        name = build_new_name(Path("old.pdf"), "Название", "Иванов И. И.", "2019",
                              template="{title}-{year}")
        self.assertEqual(name, "Название-2019.pdf")

    def test_custom_template_empty_values_cleaned(self):
        self.assertEqual(
            build_new_name(Path("old.pdf"), "Название", "", "",
                           template="{author}-{title}-{year}"),
            "Название.pdf")
        self.assertEqual(
            build_new_name(Path("old.pdf"), "Название", "", "2019",
                           template="{title} [{year}]"),
            "Название [2019].pdf")

    def test_default_template_unchanged(self):
        name = build_new_name(Path("old.pdf"), "Название", "Иванов И. И.", "2019")
        self.assertEqual(name, "Иванов И. И. - Название [2019].pdf")


if __name__ == "__main__":
    unittest.main()
