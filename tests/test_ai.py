"""Тесты ИИ-разбора обложки (--ai): сеть подменяется, без реальных запросов."""

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from titlemark.ai import (
    AiConfig,
    build_prompt,
    enrich_with_ai,
    parse_json_answer,
)
from titlemark.models import DocumentInfo, Source
from titlemark.renamer import plan_rename

AI_ANSWER = {"title": "A History of Modern Computing",
             "author": "Paul E. Ceruzzi", "year": "2004"}


def _fake_response(config, payload: dict) -> dict:
    """Ответ эндпоинта /chat/completions."""
    return {"choices": [{"message": {"content": json.dumps(AI_ANSWER, ensure_ascii=False)}}]}


class TestParseAnswer(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_json_answer('{"title": "Книга"}'), {"title": "Книга"})

    def test_markdown_fence(self):
        text = '```json\n{"title": "Книга", "author": "Автор"}\n```'
        self.assertEqual(parse_json_answer(text)["title"], "Книга")

    def test_text_around_json(self):
        text = 'Вот ответ:\n{"title": "Книга"}\nГотово.'
        self.assertEqual(parse_json_answer(text), {"title": "Книга"})

    def test_garbage(self):
        self.assertEqual(parse_json_answer("не понял вопрос"), {})
        self.assertEqual(parse_json_answer(""), {})


class TestEnrichWithAi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "00acaf02b9dfa6495f4842bd5de2a675"
        self.path.write_bytes(b"%PDF-1.4 stub")
        self.info = DocumentInfo(path=self.path, title="Черновик черновика")

    def test_ai_overrides_heuristics(self):
        with mock.patch("titlemark.ai._request", side_effect=_fake_response), \
             mock.patch("titlemark.ai.render_cover", return_value=b"png-bytes"):
            ok = enrich_with_ai(self.path, self.info, AiConfig(api_key="k"))
        self.assertTrue(ok)
        self.assertEqual(self.info.title, "A History of Modern Computing")
        self.assertEqual(self.info.author, "Paul E. Ceruzzi")
        self.assertEqual(self.info.year, "2004")
        self.assertIs(self.info.title_source, Source.AI)

    def test_cover_attached_as_image(self):
        captured = {}

        def fake_request(config, payload):
            captured.update(payload)
            return _fake_response(config, payload)

        with mock.patch("titlemark.ai._request", side_effect=fake_request), \
             mock.patch("titlemark.ai.render_cover", return_value=b"png-bytes"):
            enrich_with_ai(self.path, self.info, AiConfig(api_key="k"))
        content = captured["messages"][1]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["type"], "image_url")
        self.assertIn("base64", content[0]["image_url"]["url"])

    def test_text_only_when_no_cover(self):
        captured = {}

        def fake_request(config, payload):
            captured.update(payload)
            return _fake_response(config, payload)

        with mock.patch("titlemark.ai._request", side_effect=fake_request), \
             mock.patch("titlemark.ai.render_cover", return_value=None):
            enrich_with_ai(self.path, self.info, AiConfig(api_key="k"))
        self.assertIsInstance(captured["messages"][1]["content"], str)
        self.assertTrue(any("cover" in w for w in self.info.warnings))

    def test_network_error_keeps_heuristics(self):
        with mock.patch("titlemark.ai.render_cover", return_value=b"png"), \
             mock.patch("titlemark.ai._request",
                        side_effect=urllib.error.URLError("нет сети")):
            ok = enrich_with_ai(self.path, self.info, AiConfig(api_key="k"))
        self.assertFalse(ok)
        self.assertEqual(self.info.title, "Черновик черновика")   # не тронуто
        self.assertTrue(any("the AI did not respond" in w for w in self.info.warnings))

    def test_prompt_contains_hints(self):
        self.info.title_candidates = [("Кандидат один", 5.0)]
        prompt = build_prompt(self.info)
        self.assertIn("Черновик черновика", prompt)
        self.assertIn("Кандидат один", prompt)


class TestPlanWithAi(unittest.TestCase):
    def test_plan_rename_uses_ai_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "00acaf02b9dfa6495f4842bd5de2a675"
            p.write_bytes(b"%PDF-1.4 stub")
            with mock.patch("titlemark.ai._request", side_effect=_fake_response), \
                 mock.patch("titlemark.ai.render_cover", return_value=b"png"):
                plan = plan_rename(p, use_ocr=False, ai=AiConfig(api_key="k"))
            self.assertEqual(plan.status, "ok")
            self.assertEqual(
                plan.new_name,
                "Paul E. Ceruzzi - A History of Modern Computing [2004].pdf")


class TestCliAi(unittest.TestCase):
    def test_cloud_requires_key(self):
        from titlemark.cli import main

        with tempfile.NamedTemporaryFile(suffix=".pdf") as fh:
            code = main(["--ai", fh.name])
        self.assertEqual(code, 2)

    def test_local_needs_no_key(self):
        from titlemark.cli import main

        with tempfile.NamedTemporaryFile(suffix=".pdf") as fh:
            code = main(["--ai", "--ai-url", "http://localhost:11434/v1",
                         "--no-ocr", fh.name])
        # без ключа локальный запуск проходит валидацию (сеть в тесте не ходим:
        # ИИ вернёт ошибку — это warning, не падение)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
