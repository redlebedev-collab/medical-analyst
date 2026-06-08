"""
backends.py — абстракция над LLM-бэкендами.

Поддерживаемые режимы:
  - anthropic  : облачный Claude API (нужен ANTHROPIC_API_KEY)
  - ollama     : локальная модель через Ollama (нужен запущенный ollama serve)

Использование:
    from backends import get_backend, LLMBackend

    backend = get_backend("anthropic", api_key="sk-ant-...")
    response = backend.chat(system="...", user="...")
"""

from __future__ import annotations
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Базовый класс
# ---------------------------------------------------------------------------

@dataclass
class LLMBackend(ABC):
    """Единый интерфейс для всех бэкендов."""
    model: str = ""

    @abstractmethod
    def chat(self, user: str, system: str = "", max_tokens: int = 8192) -> str:
        """Отправляет сообщение, возвращает текст ответа."""
        ...

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Проверяет доступность бэкенда. Возвращает (ok, сообщение)."""
        ...


# ---------------------------------------------------------------------------
# Anthropic (облачный)
# ---------------------------------------------------------------------------

@dataclass
class AnthropicBackend(LLMBackend):
    model: str = "claude-sonnet-4-6"
    api_key: str = ""

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def _client(self):
        try:
            import anthropic
            return anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("Установите: pip install anthropic")

    def chat(self, user: str, system: str = "", max_tokens: int = 8192) -> str:
        client = self._client()
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
        )
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        return response.content[0].text

    def is_available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API-ключ не задан"
        if not self.api_key.startswith("sk-ant-"):
            return False, "Ключ выглядит некорректно (должен начинаться с sk-ant-)"
        try:
            import anthropic  # noqa
        except ImportError:
            return False, "Библиотека anthropic не установлена: pip install anthropic"
        # Лёгкая проверка без реального запроса
        return True, f"Готов ({self.model})"


# ---------------------------------------------------------------------------
# Ollama (локальный)
# ---------------------------------------------------------------------------

OLLAMA_DEFAULT_MODEL = "llama3.1"
OLLAMA_BASE_URL = "http://localhost:11434"

@dataclass
class OllamaBackend(LLMBackend):
    model: str = OLLAMA_DEFAULT_MODEL
    base_url: str = OLLAMA_BASE_URL

    def chat(self, user: str, system: str = "", max_tokens: int = 8192) -> str:
        try:
            import ollama
        except ImportError:
            raise ImportError("Установите: pip install ollama")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        client = ollama.Client(host=self.base_url)
        response = client.chat(
            model=self.model,
            messages=messages,
            options={"num_predict": max_tokens},
        )
        return response["message"]["content"]

    def list_models(self) -> list[str]:
        """Возвращает список доступных локальных моделей."""
        try:
            import ollama
            client = ollama.Client(host=self.base_url)
            models = client.list()
            return [m["name"] for m in models.get("models", [])]
        except Exception:
            return []

    def is_available(self) -> tuple[bool, str]:
        try:
            import ollama  # noqa
        except ImportError:
            return False, "Библиотека ollama не установлена: pip install ollama"

        models = self.list_models()
        if not models:
            return False, (
                "Ollama не запущен или нет загруженных моделей.\n"
                "Запустите: ollama serve\n"
                f"Загрузите модель: ollama pull {OLLAMA_DEFAULT_MODEL}"
            )
        if self.model not in models:
            # Автовыбор первой доступной
            self.model = models[0]
        return True, f"Готов ({self.model})"


# ---------------------------------------------------------------------------
# Фабрика
# ---------------------------------------------------------------------------

def get_backend(
    mode: str,
    api_key: str = "",
    model: str = "",
    ollama_url: str = OLLAMA_BASE_URL,
) -> LLMBackend:
    """
    Создаёт бэкенд по режиму.

    Args:
        mode: "anthropic" или "ollama"
        api_key: API-ключ Anthropic (только для режима anthropic)
        model: название модели (если пусто — используется default)
        ollama_url: адрес Ollama (по умолчанию localhost:11434)
    """
    if mode == "anthropic":
        return AnthropicBackend(
            model=model or "claude-sonnet-4-6",
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
        )
    elif mode == "ollama":
        return OllamaBackend(
            model=model or OLLAMA_DEFAULT_MODEL,
            base_url=ollama_url,
        )
    else:
        raise ValueError(f"Неизвестный режим: {mode}. Используйте 'anthropic' или 'ollama'.")


# ---------------------------------------------------------------------------
# Системный промпт (общий для всех бэкендов)
# ---------------------------------------------------------------------------

SYSTEM_ANALYST = """
Ты — аналитик медицинских данных. НЕ врач, НЕ клиницист.

ЖЁСТКИЕ ПРАВИЛА:
1. Никаких диагнозов. Только «стоит обсудить с врачом [специальность]».
2. Каждая рекомендация — со ссылкой на гайдлайн (организация, год, Class/Level).
3. Нейтральный регистр. Запрещены: «СРОЧНО», «критично». Только P1/P2/P3.
4. Конфликты гайдлайнов — показывать оба варианта.
5. Обязательный раздел «Что не делаем и почему».

Начни ответ с дисклеймера:
«Документ подготовлен аналитическим инструментом, не врачом.
Все выводы требуют обсуждения с лечащим специалистом.»
""".strip()
