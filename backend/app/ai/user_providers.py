"""Proveedores IA con API key por llamada (cuota del usuario).

A diferencia de app/ai/providers/* (keys globales del .env para tareas
del sistema), estos reciben la key del USUARIO en cada llamada: jamas
tocan las globales. Registro extensible: nuevos proveedores se agregan
en SUPPORTED sin tocar el resto.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Fallo clasificado: code en auth|quota|rate|unavailable|unknown."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def classify_http_error(status: int | None, body: str,
                        exc_name: str) -> ProviderError:
    """HTTP/timeout -> ProviderError con codigo estable."""
    text = f"{body or ''}"[:500]
    lowered = text.lower()
    if status in (401, 403) or "invalid_api_key" in lowered \
            or "invalid api key" in lowered \
            or "api key not valid" in lowered \
            or "incorrect api key" in lowered \
            or "authentication" in lowered and status in (401, 403):
        return ProviderError(
            "auth", f"API key rechazada (auth {status or '?'})")
    # Sin saldo (DeepSeek 402 "Insufficient Balance", OpenAI
    # insufficient_quota): la key es VALIDA, solo falta recarga.
    if status == 402 or "insufficient" in lowered:
        return ProviderError("quota", f"Sin saldo: {text[:200]}")
    if status == 429 or "rate" in exc_name.lower():
        if "quota" in lowered or "insufficient" in lowered \
                or "exceeded" in lowered:
            return ProviderError("quota", f"Cuota agotada: {text[:200]}")
        return ProviderError("rate", f"Rate limit: {text[:200]}")
    if status and 500 <= status < 600:
        return ProviderError(
            "unavailable", f"Proveedor no disponible ({status})")
    if "timeout" in exc_name.lower() or "timeout" in lowered \
            or "connect" in lowered:
        return ProviderError("unavailable", "Timeout/conexion fallida")
    return ProviderError("unknown", f"{exc_name}: {text[:200]}")


class UserProviderSpec:
    """Un proveedor usable con key de usuario (OpenAI-compatible o REST)."""

    id: str = ""
    label: str = ""
    model: str = ""
    key_help: str = ""
    key_prefix_hint: str = ""

    def complete(self, system: str, user: str, api_key: str,
                 timeout: int) -> str:
        """Devuelve el texto (idealmente JSON). Lanza ProviderError."""
        raise NotImplementedError

    def _chat_openai_compatible(self, base_url: str, api_key: str,
                                model: str, system: str, user: str,
                                timeout: int,
                                extra_headers: dict | None = None,
                                json_mode: bool = True) -> str:
        """Chat OpenAI-compatible (json_mode=False si el modelo no
        soporta response_format: el prompt ya exige JSON exclusivo)."""
        import httpx

        headers = {"Authorization": f"Bearer {api_key}"}
        headers.update(extra_headers or {})
        payload: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise classify_http_error(None, "", type(exc).__name__)
        if response.status_code != 200:
            raise classify_http_error(
                response.status_code, response.text, "HTTPStatusError")
        try:
            text = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("unknown", f"Respuesta inesperada: {exc}")
        if not text or not str(text).strip():
            raise ProviderError("unknown", "Respuesta vacia")
        return str(text)


class GeminiUserProvider(UserProviderSpec):
    id = "gemini"
    label = "Gemini"
    model = "gemini-3.8-flash"
    key_help = "Google AI Studio (aistudio.google.com → Get API Key)"
    key_prefix_hint = "AIza"

    def complete(self, system: str, user: str, api_key: str,
                 timeout: int) -> str:
        import httpx

        import os as _os

        # GEMINI_MODEL permite cambiarlo sin tocar codigo (los modelos
        # viejos los da de baja Google: 2.0-flash murio el 2026-06-01).
        model = (_os.getenv("GEMINI_MODEL") or type(self).model).strip() \
            or type(self).model
        url = ("https://generativelanguage.googleapis.com/v1beta/"
               f"models/{model}:generateContent")
        try:
            response = httpx.post(
                url,
                params={"key": api_key},
                headers={"Content-Type": "application/json",
                         "x-goog-api-key": api_key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": user}]}],
                    "generationConfig": {"responseMimeType": "application/json",
                                         "temperature": 0.2},
                },
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise classify_http_error(None, "", type(exc).__name__)
        if response.status_code != 200:
            raise classify_http_error(
                response.status_code, response.text, "HTTPStatusError")
        try:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("unknown", f"Respuesta inesperada: {exc}")
        if not text or not str(text).strip():
            raise ProviderError("unknown", "Respuesta vacia")
        return str(text)


class DeepSeekUserProvider(UserProviderSpec):
    id = "deepseek"
    label = "DeepSeek"
    model = "deepseek-chat"
    key_help = "platform.deepseek.com → API keys (empieza con sk-)"
    key_prefix_hint = "sk-"

    def complete(self, system: str, user: str, api_key: str,
                 timeout: int) -> str:
        return self._chat_openai_compatible(
            "https://api.deepseek.com", api_key, self.model,
            system, user, timeout)


class GroqUserProvider(UserProviderSpec):
    id = "groq"
    label = "Groq"
    model = "openai/gpt-oss-120b"
    key_help = "console.groq.com → API Keys (gratis, empieza con gsk_)"
    key_prefix_hint = "gsk_"

    def complete(self, system: str, user: str, api_key: str,
                 timeout: int) -> str:
        return self._chat_openai_compatible(
            "https://api.groq.com/openai/v1", api_key, self.model,
            system, user, timeout, json_mode=False)


class OpenRouterUserProvider(UserProviderSpec):
    id = "openrouter"
    label = "OpenRouter"
    model = "deepseek/deepseek-chat-v3-0324:free"
    key_help = ("openrouter.ai → Keys (gratis, empieza con sk-or-). Usa "
                "modelos :free como deepseek o qwen sin costo.")
    key_prefix_hint = "sk-or-"

    def complete(self, system: str, user: str, api_key: str,
                 timeout: int) -> str:
        return self._chat_openai_compatible(
            "https://openrouter.ai/api/v1", api_key, self.model,
            system, user, timeout, json_mode=False,
            extra_headers={"HTTP-Referer": "https://job-agent-puce-eight.vercel.app",
                           "X-Title": "Job Agent"})


class OpenAIUserProvider(UserProviderSpec):
    id = "openai"
    label = "OpenAI"
    model = "gpt-4o-mini"
    key_help = "platform.openai.com → API keys (empieza con sk-)"
    key_prefix_hint = "sk-"

    def complete(self, system: str, user: str, api_key: str,
                 timeout: int) -> str:
        return self._chat_openai_compatible(
            "https://api.openai.com/v1", api_key, self.model,
            system, user, timeout)


SUPPORTED: dict[str, UserProviderSpec] = {
    spec.id: spec for spec in (
        GeminiUserProvider(), DeepSeekUserProvider(), OpenAIUserProvider(),
        GroqUserProvider(), OpenRouterUserProvider())
}


def register_provider(spec: UserProviderSpec) -> None:
    """Extiende proveedores sin tocar este modulo (futuros)."""
    SUPPORTED[spec.id] = spec


def get_spec(provider_id: str) -> UserProviderSpec:
    try:
        return SUPPORTED[provider_id]
    except KeyError:
        raise ValueError(
            f"Proveedor desconocido: {provider_id}. "
            f"Soportados: {', '.join(sorted(SUPPORTED))}")
