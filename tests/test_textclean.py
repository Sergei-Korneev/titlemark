"""Тесты textclean: мусорные заголовки, очистка, качество текста."""

import unittest

from titlemark.textclean import (
    TextQuality,
    clean_author,
    clean_title,
    is_junk_title,
    text_quality,
)


class TestJunkTitle(unittest.TestCase):
    def test_artifacts(self):
        for junk in ("Layout 1", "Untitled", "scan 5", "Microsoft Word -",
                     "43b2956cd82bc62159778acf98779b88", "29623753",
                     "d60fa09a-c4b5-4e31-9dbd-5d049c6c8f49",
                     "Pamyat_text 02.indd", "vocabulary.docx", "Оглавление"):
            self.assertTrue(is_junk_title(junk), junk)

    def test_publisher_and_print_junk(self):
        for junk in ("Москва · Санкт-Петербург", "Москва, 2014",
                     "BIRMINGHAM - MUMBAI", "Kindle Direct Publishing",
                     '"Издательство Наука и Техника"', "МЦНМО",
                     "Beijing Boston Farnham Sebastopol Tokyo",
                     "New York London", "D N N O 2 TI", "Table of Contents",
                     "1. ВВЕДЕНИЕ", "2.3 ОСНОВНЫЕ ПОНЯТИЯ", "1 of 4",
                     "1 of 4 2:14:26, 7:47 PM", "Издательство «Манн»"):
            self.assertTrue(is_junk_title(junk), junk)

    def test_numbered_real_title_kept(self):
        for good in ("40 алгоритмов Python", "100 ошибок Go",
                     "2. издание переработанное", "2001: A Space Odyssey"):
            self.assertFalse(is_junk_title(good), good)

    def test_real_titles_kept(self):
        for good in ("Современная английская грамматика",
                     "ГОСТ Р МЭК 62443-2-1-2015",
                     "Docker Deep Dive",
                     "Как приручить Linux capabilities в Kubernetes",
                     "ПОМНИТЬ ВСЕ", "Весь Linux. Для тех, кто хочет стать"):
            self.assertFalse(is_junk_title(good), good)


class TestCleanTitle(unittest.TestCase):
    def test_strip_prefixes(self):
        self.assertEqual(
            clean_title("Скачать ГОСТ Р МЭК 62443-2-1-2015 Сети"),
            "ГОСТ Р МЭК 62443-2-1-2015 Сети",
        )
        self.assertEqual(clean_title("Microsoft Word - vocabulary.docx"),
                         "vocabulary")
        self.assertEqual(clean_title("English Idioms in use-Advanced - Unknown"),
                         "English Idioms in use-Advanced - Unknown")
        self.assertEqual(clean_title("1С 8.2-8.3. Приемы разработки, FAQ - Google Документы"),
                         "1С 8.2-8.3. Приемы разработки, FAQ")
        self.assertEqual(clean_title("epdf.pub english-collocations"),
                         "english-collocations")
        self.assertEqual(clean_title("Alas, Babylon (Z-Library)"), "Alas, Babylon")

    def test_underscores_and_spaces(self):
        self.assertEqual(clean_title("Как_приручить_Linux  capabilities"),
                         "Как приручить Linux capabilities")

    def test_watermark_and_symbols(self):
        self.assertEqual(clean_title("Психология глупости @bookinier"),
                         "Психология глупости")
        self.assertEqual(clean_title("ВРЕМЯ UNIX®"), "ВРЕМЯ UNIX")


class TestTextQuality(unittest.TestCase):
    def test_good_text(self):
        text = "Современная английская грамматика\nПрактическое пособие\nМосква 2019"
        self.assertIs(text_quality(text), TextQuality.GOOD)

    def test_empty(self):
        self.assertIs(text_quality(""), TextQuality.EMPTY)
        self.assertIs(text_quality("   \n\t "), TextQuality.EMPTY)

    def test_mojibake_latin1(self):
        text = "£¤¦£© «§¤§¸« ¨«§¡©¦ ©¡® ®¡©·¡©·¡©µ"
        self.assertIs(text_quality(text), TextQuality.GARBAGE)

    def test_mojibake_ipa(self):
        text = "ɍȾɄ Ʉɚɪɚɛɚɧɶ Ⱥ ȼ Ƚɭɞɡɟɧɤɨ\nɊɡɩɪɨɜɟɡɬɢ"
        self.assertIs(text_quality(text), TextQuality.GARBAGE)

    def test_replacement_chars(self):
        self.assertIs(text_quality("Title \ufffd\ufffd\ufffd book"), TextQuality.GARBAGE)

    def test_fragmented_text(self):
        text = ("E\nD N\nN O\n2 TI\nW ICKED COOL\nSHELL SCRIP T S\n"
                "SCCR R II P\nPTTS\nS FF OO RR LL II N NU UX X\n"
                "OO NN TT HH EE WW WW WW\nA UU TH HO OR R\n")
        self.assertIs(text_quality(text), TextQuality.GARBAGE)

    def test_normal_short_words_ok(self):
        text = ("This comprehensive book is about the shell and it goes on "
                "and on with practical examples of administration tasks")
        self.assertIs(text_quality(text), TextQuality.GOOD)


class TestCleanAuthor(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(clean_author("Colleen Hoover"), "Colleen Hoover")
        self.assertEqual(clean_author("Иванов И. И."), "Иванов И. И.")
        self.assertEqual(clean_author("James Patterson and Maxine Paetro"),
                         "James Patterson and Maxine Paetro")

    def test_junk(self):
        for junk in ("Test", ".", "-", "admin", "Adobe", "", "123",
                     "unknown", "Microsoft", "Сборник", "Коллектив"):
            self.assertEqual(clean_author(junk), "", junk)

    def test_caps_normalized(self):
        self.assertEqual(clean_author("АРТУР ДУМЧЕВ"), "Артур Думчев")
        self.assertEqual(clean_author("BLAKE CROUCH"), "Blake Crouch")

    def test_initials_not_stopwords(self):
        # «О.» — инициал, а не предлог «о»
        self.assertEqual(clean_author("О. Б. ЛУПАНОВА"), "О. Б. Лупанова")
        self.assertEqual(clean_author("В. В. Ситель"), "В. В. Ситель")

    def test_long_is_junk(self):
        self.assertEqual(clean_author("a" * 80), "")
        self.assertEqual(clean_author("one two three four five six seven"), "")


if __name__ == "__main__":
    unittest.main()
