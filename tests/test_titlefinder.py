"""Тесты эвристик выбора заголовка и автора из текста."""

import unittest

from shelfmark.titlefinder import (
    find_author,
    find_title,
    looks_like_author,
    merge_title,
)

COVER_RU = [
    "                              Современная английская грамматика",
    "                    Практическое пособие для студентов и преподавателей",
    "",
    "                          Иванова Елена Петровна",
    "",
    "                                  Москва 2019",
    "Содержание",
    "Chapter 1. Nouns and verbs in modern English language today begins here",
]

COVER_EN = [
    "                        ENGLISH IDIOMS IN USE",
    "                       Advanced",
    "                          by Felicity O'Dell",
    "                       CAMBRIDGE UNIVERSITY PRESS",
]


class TestFindTitle(unittest.TestCase):
    def test_russian_cover(self):
        title, score, _ = find_title(COVER_RU)
        self.assertIn("Современная английская грамматика", title)
        self.assertGreater(score, 2.0)

    def test_english_cover(self):
        title, _, _ = find_title(COVER_EN)
        self.assertIn("ENGLISH IDIOMS IN USE", title)

    def test_service_lines_rejected(self):
        lines = ["ISBN 978-5-00000-000-0", "© ООО «Издательство», 2019",
                 "http://example.com", "УДК 811.111(075.8)"]
        title, _, _ = find_title(lines)
        self.assertEqual(title, "")

    def test_author_line_not_title(self):
        lines = ["by Felicity O'Dell", "Иванов И. И.", "Содержание"]
        title, _, _ = find_title(lines)
        self.assertEqual(title, "")

    def test_empty(self):
        title, _, _ = find_title([])
        self.assertEqual(title, "")

    def test_candidates_returned(self):
        _, _, candidates = find_title(COVER_RU)
        self.assertLessEqual(len(candidates), 10)
        self.assertTrue(candidates)


class TestFindAuthor(unittest.TestCase):
    def test_by_line(self):
        self.assertEqual(find_author(COVER_EN), "Felicity O'Dell")

    def test_initials(self):
        self.assertEqual(find_author(COVER_RU), "Иванова Елена Петровна")

    def test_initials_first(self):
        lines = ["КЛИНКА, ЕТЮЛОПЯ ТА ПАТОГЕНЕЗ", "Н. В. Карабань, А. В. Гудзенко"]
        self.assertEqual(find_author(lines), "Н. В. Карабань, А. В. Гудзенко")

    def test_initials_first_caps_surname(self):
        # «под редакцией О. Б. ЛУПАНОВА» — редактор, а не название
        lines = ["Кибернетический сборник", "О. Б. ЛУПАНОВА", "ИЗДАТЕЛЬСТВО «МИР»"]
        title, _, _ = find_title(lines)
        self.assertIn("Кибернетический", title)
        self.assertEqual(find_author(lines, exclude_title=title), "О. Б. ЛУПАНОВА")

    def test_editor_label_is_not_author(self):
        # «под редакцией» — служебная подпись, а не имя
        lines = ["Кибернетический сборник", "под редакцией", "О. Б. ЛУПАНОВА"]
        self.assertEqual(find_author(lines), "О. Б. ЛУПАНОВА")

    def test_caps_name_not_title(self):
        lines = ["АРТУР ДУМЧЕВ", "ПОМНИТЬ ВСЕ",
                 "ПРАКТИЧЕСКОЕ РУКОВОДСТВО",
                 "Издательство «Манн, Иванов и Фербер»"]
        title, _, _ = find_title(lines)
        self.assertEqual(title, "ПОМНИТЬ ВСЕ")
        self.assertEqual(find_author(lines, exclude_title=title), "АРТУР ДУМЧЕВ")

    def test_caps_title_with_caps_author(self):
        lines = ["DARK MATTER", "BLAKE CROUCH", "A NOVEL"]
        title, _, _ = find_title(lines)
        self.assertEqual(title, "DARK MATTER")

    def test_person_title_fallback(self):
        # обложка, где и заголовок, и автор — имена: спасает запасной проход
        lines = ["АННА КАРЕНИНА", "ЛЕВ ТОЛСТОЙ", "Роман"]
        title, _, _ = find_title(lines)
        self.assertEqual(title, "АННА КАРЕНИНА")
        self.assertEqual(find_author(lines, exclude_title=title), "ЛЕВ ТОЛСТОЙ")

    def test_english_person_author(self):
        lines = ["IT ENDS WITH US", "Colleen Hoover"]
        title, _, _ = find_title(lines)
        self.assertEqual(title, "IT ENDS WITH US")
        self.assertEqual(find_author(lines, exclude_title=title), "Colleen Hoover")

    def test_no_author(self):
        self.assertEqual(find_author(["Только заголовок и больше ничего"]), "")

    def test_looks_like_author(self):
        self.assertTrue(looks_like_author("by Colleen Hoover"))
        self.assertTrue(looks_like_author("Автор: Пушкин А. С."))
        self.assertTrue(looks_like_author("Иванов Иван Иванович"))
        self.assertTrue(looks_like_author("АРТУР ДУМЧЕВ"))
        self.assertFalse(looks_like_author("Современная английская грамматика"))


class TestMergeTitle(unittest.TestCase):
    def test_merge_continuation(self):
        lines = ["ENGLISH IDIOMS IN USE", "Advanced", "by Felicity O'Dell"]
        merged = merge_title(lines, "ENGLISH IDIOMS IN USE")
        self.assertEqual(merged, "ENGLISH IDIOMS IN USE Advanced")

    def test_no_merge_with_author(self):
        lines = ["Some Book Title", "by John Smith"]
        self.assertEqual(merge_title(lines, "Some Book Title"), "Some Book Title")

    def test_merge_titlecase_subtitle(self):
        lines = ["UNIX", "A History and a Memoir", "Brian Kernighan"]
        self.assertEqual(merge_title(lines, "UNIX"), "UNIX A History and a Memoir")


if __name__ == "__main__":
    unittest.main()
