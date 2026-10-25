"""Тесты принудительного OCR (--force-ocr)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shelfmark.extractors.base import Extractor
from shelfmark.models import Source
from shelfmark.renamer import plan_rename


class _StubExtractor(Extractor):
    """Файл с хорошим текстовым слоем, но кривым содержимым (по мнению юзера)."""

    extensions = (".stub",)
    ocr_capable = True

    def read_metadata(self, path: Path) -> tuple[str, str, str]:
        return "", "", ""

    def read_text(self, path: Path, max_pages: int = 3) -> str:
        return "Современная английская грамматика"


OCR_TEXT = "ПРАВИЛЬНОЕ НАЗВАНИЕ ИЗ OCR\nПОДЗАГОЛОВОК"


class TestForceOcr(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "29623753.stub"
        self.path.write_bytes(b"stub")

    def test_force_ocr_uses_ocr_text(self):
        with mock.patch("shelfmark.ocr.ocr_first_pages", return_value=OCR_TEXT) as m:
            info = _StubExtractor().extract(self.path, use_ocr=True, force_ocr=True)
        self.assertTrue(m.called)
        self.assertIs(info.title_source, Source.OCR)
        self.assertIn("ПРАВИЛЬНОЕ НАЗВАНИЕ ИЗ OCR", info.title)

    def test_without_force_text_layer_wins(self):
        with mock.patch("shelfmark.ocr.ocr_first_pages", return_value=OCR_TEXT) as m:
            info = _StubExtractor().extract(self.path, use_ocr=True, force_ocr=False)
        self.assertFalse(m.called)               # текст хороший — OCR не нужен
        self.assertIs(info.title_source, Source.TEXT)
        self.assertEqual(info.title, "Современная английская грамматика")

    def test_force_ocr_empty_result_falls_back(self):
        with mock.patch("shelfmark.ocr.ocr_first_pages", return_value="   "):
            info = _StubExtractor().extract(self.path, use_ocr=True, force_ocr=True)
        self.assertIs(info.title_source, Source.TEXT)
        self.assertTrue(any("OCR produced no text" in w for w in info.warnings))

    def test_force_ocr_beats_metadata(self):
        class MetaStub(_StubExtractor):
            def read_metadata(self, path: Path) -> tuple[str, str, str]:
                return "Черновик черновика", "", ""

        with mock.patch("shelfmark.ocr.ocr_first_pages", return_value=OCR_TEXT):
            info = MetaStub().extract(self.path, use_ocr=True, force_ocr=True)
        self.assertIs(info.title_source, Source.OCR)

    def test_plan_rename_force_ocr_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "00acaf02b9dfa6495f4842bd5de2a675"
            p.write_bytes(b"%PDF-1.4 stub")
            with mock.patch("shelfmark.ocr.ocr_first_pages", return_value=OCR_TEXT):
                plan = plan_rename(p, use_ocr=True, force_ocr=True)
            self.assertEqual(plan.status, "ok")
            self.assertTrue(plan.new_name.endswith(".pdf"))
            self.assertIn("ПРАВИЛЬНОЕ НАЗВАНИЕ ИЗ OCR", plan.new_name)


if __name__ == "__main__":
    unittest.main()
