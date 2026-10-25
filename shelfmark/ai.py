"""Интеграция с vision-LLM (OpenAI-совместимый API) для разбора обложки.

ИИ включается только явным флагом (--ai): утилита рендерит первую страницу
в картинку, показывает её модели вместе с кандидатами эвристик и получает
строгий JSON {"title", "author", "year"}. Понимает любые совместимые
эндпоинты: OpenAI, DeepSeek, GigaChat, YandexGPT, локальная Ollama
(http://localhost:11434/v1), llama.cpp, vLLM.

Внешних библиотек нет — только стандартная библиотека.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .models import DocumentInfo, Source

DEFAULT_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "Ты — библиографический ассистент. По обложке или титулу документа "
    "определи точное название, автора и год издания. "
    "Ответь СТРОГО одним JSON-объектом вида "
    '{"title": "...", "author": "...", "year": "YYYY"} без пояснений и markdown. '
    "Название — на языке оригинала, ровно как на обложке (без служебных слов "
    "вида «Скачать», «читать онлайн»). Автор — полное имя, как на обложке. "
    "Если данных нет — пустая строка."
)


@dataclass
class AiConfig:
    """Параметры подключения к ИИ."""

    url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    api_key: str = ""
    timeout: int = 60

    @property
    def is_local(self) -> bool:
        return "localhost" in self.url or "127.0.0.1" in self.url


# ---------------------------------------------------------------------------
# обложка
# ---------------------------------------------------------------------------

def render_cover(path: Path, page: int = 1, dpi: int = 150) -> bytes | None:
    """Отрендерить страницу документа в PNG (pdftoppm) или None."""
    if not shutil.which("pdftoppm"):
        return None
    with tempfile.TemporaryDirectory(prefix="shelfmark_ai_") as tmp:
        out = Path(tmp) / "cover"
        try:
            subprocess.run(
                ["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi),
                 "-png", "-singlefile", str(path), str(out)],
                capture_output=True, timeout=60, check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        img = Path(tmp) / "cover.png"
        return img.read_bytes() if img.exists() else None


# ---------------------------------------------------------------------------
# запрос и разбор ответа
# ---------------------------------------------------------------------------

def build_prompt(info: DocumentInfo) -> str:
    """Текстовая часть запроса: подсказки от эвристик."""
    lines = [f"Имя файла: {info.path.name}"]
    if info.title:
        lines.append(f"Что определили эвристики (может быть ошибкой): {info.title}")
    if info.author:
        lines.append(f"Предполагаемый автор: {info.author}")
    if info.year:
        lines.append(f"Предполагаемый год: {info.year}")
    if info.title_candidates:
        cands = "; ".join(c for c, _s in info.title_candidates[:5])
        lines.append(f"Кандидаты в заголовок из текста: {cands}")
    if info.text_snippet:
        lines.append(f"Фрагмент текста: {info.text_snippet[:300]}")
    return "\n".join(lines)


def _request(config: AiConfig, payload: dict) -> dict:
    """POST /chat/completions. Выделено для подмены в тестах."""
    url = config.url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST",
    )
    with urllib.request.urlopen(req, timeout=config.timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_json_answer(text: str) -> dict:
    """Достать JSON-объект из ответа модели (терпимо к markdown-обёрткам)."""
    if not text:
        return {}
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    m = re.search(r"\{.*?\}", cleaned, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _apply_answer(info: DocumentInfo, data: dict) -> bool:
    """Перенести поля ответа в DocumentInfo (пустые значения не мешают)."""
    changed = False
    for key, attr in (("title", "title"), ("author", "author"), ("year", "year")):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            setattr(info, attr, value.strip())
            changed = True
    if changed:
        if info.title:
            info.title_source = Source.AI
        if info.author:
            info.author_source = Source.AI
    return changed


def enrich_with_ai(path: Path, info: DocumentInfo, config: AiConfig) -> bool:
    """Спросить ИИ про обложку и обновить info. False — ИИ не ответил."""
    cover = render_cover(path)
    prompt = build_prompt(info)

    if cover:
        content: str | list = [{
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,"
                       + base64.b64encode(cover).decode("ascii"),
            },
        }, {"type": "text", "text": prompt}]
    else:
        info.warnings.append("could not render the cover — the AI got text only")
        content = prompt

    payload = {
        "model": config.model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    }

    try:
        data = _request(config, payload)
        answer = data["choices"][0]["message"]["content"]
    except (urllib.error.URLError, OSError, KeyError, IndexError,
            json.JSONDecodeError, ValueError) as exc:
        info.warnings.append(f"the AI did not respond: {exc}")
        return False

    parsed = parse_json_answer(answer)
    if not _apply_answer(info, parsed):
        info.warnings.append("the AI returned no recognized data")
        return False
    return True
