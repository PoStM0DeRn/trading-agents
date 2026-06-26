import os
import json
import re
import time
import logging
from typing import Optional, Callable
from config.secrets import secrets

import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class LMStudioClient:
    """Обёртка над LM Studio API (OpenAI-совместимый)."""

    def __init__(
        self,
        host: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        on_request: Optional[Callable] = None,
    ):
        self.host = host or secrets.LMSTUDIO_HOST
        self.model = model or os.getenv("LMSTUDIO_MODEL", "default")
        self.temperature = temperature
        self._on_request = on_request

        self._client = OpenAI(
            base_url=f"{self.host}/v1",
            api_key="lm-studio",
        )
        self._http = httpx.Client(base_url=self.host, timeout=120.0)

    def set_on_request(self, callback: Callable):
        """Установить callback для трекинга запросов."""
        self._on_request = callback

    def close(self):
        try:
            self._http.close()
        except Exception:
            pass

    def ensure_available(self) -> bool:
        """Проверить доступность LM Studio, переподключиться при ошибке."""
        try:
            resp = self._http.get("/v1/models", timeout=5.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass

        logger.warning("LM Studio unavailable. Reconnecting...")
        try:
            self.close()
            self._http = httpx.Client(base_url=self.host, timeout=120.0)
            self._client = OpenAI(
                base_url=f"{self.host}/v1",
                api_key="lm-studio",
            )
            resp = self._http.get("/v1/models", timeout=5.0)
            if resp.status_code == 200:
                logger.info("LM Studio reconnected.")
                return True
        except Exception as e:
            logger.error(f"LM Studio reconnection failed: {e}")
        return False

    def _track_request(self, response_dict: dict, elapsed: float):
        """Отправить метрику в callback."""
        if self._on_request:
            try:
                self._on_request(response_dict, elapsed)
            except Exception as e:
                logger.warning(f"Request tracker callback failed: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Генерация текста по промпту."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        start = time.time()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        elapsed = time.time() - start

        self._track_request(response.model_dump(), elapsed)
        return response.choices[0].message.content or ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> dict:
        """Чат с поддержкой tools (function calling)."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        start = time.time()
        response = self._client.chat.completions.create(**kwargs)
        elapsed = time.time() - start

        result = response.model_dump()
        self._track_request(result, elapsed)
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def generate_json(self, prompt: str, system: Optional[str] = None) -> dict:
        """Генерация JSON-ответа с авто-повтором при ошибках."""
        messages = []
        json_instruction = (
            (system or "") + "\n\nYou MUST respond with valid JSON only. "
            "No text before or after the JSON object."
        )
        messages.append({"role": "system", "content": json_instruction})
        messages.append({"role": "user", "content": prompt})

        start = time.time()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        elapsed = time.time() - start

        self._track_request(response.model_dump(), elapsed)

        content = response.choices[0].message.content or ""

        # Предварительная очистка: убираем<think>теги и markdown fences ДО первого парсинга
        cleaned_content = self._pre_clean_llm_content(content)

        try:
            return json.loads(cleaned_content)
        except json.JSONDecodeError:
            cleaned = self._fix_json(cleaned_content)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                logger.warning(f"Raw LLM content (first 500): {repr(content[:500])}")
                logger.warning(f"Cleaned content (first 500): {repr(cleaned[:500])}")
                raise ValueError(
                    f"Failed to parse JSON from LLM response: {content[:200]}"
                )

    @staticmethod
    def _pre_clean_llm_content(text: str) -> str:
        """Очистка LLM ответа от thinking тегов и markdown fences перед парсингом."""
        if not text or not text.strip():
            return text

        # Убираем</think> (Qwen/DeepSeek thinking)
        text = re.sub(r'<think>[\s\S]*?</think>', '', text)
        text = re.sub(r'</think>', '', text)

        # Убираем markdown code fences
        text = re.sub(r'```json\s*\n?', '', text)
        text = re.sub(r'```\s*\n?', '', text)

        return text.strip()

    @staticmethod
    def _fix_json(text: str) -> str:
        """Попытка исправить часто встречаемые ошибки в JSON от LLM."""
        if not text or not text.strip():
            return text

        # Извлекаем JSON
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return text
        s = match.group()

        # Убираем комментарии // и /* */
        s = re.sub(r"//[^\n]*", "", s)
        s = re.sub(r"/\*[\s\S]*?\*/", "", s)

        # Заключаем незаключённые ключи: { key: -> { "key":
        s = re.sub(r'([\{,]\s*)([a-zA-Z_]\w*)\s*:', r'\1"\2":', s)

        # Заменяем одинарные кавычки на двойные: 'value' -> "value"
        s = re.sub(r"'([^']*?)'", r'"\1"', s)

        # Убираем висячие запятые перед } или ]
        s = re.sub(r",\s*([}\]])", r"\1", s)

        return s

    def is_available(self) -> bool:
        """Проверка доступности LM Studio."""
        try:
            response = self._http.get("/v1/models")
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Список доступных моделей."""
        try:
            response = self._http.get("/v1/models")
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []
