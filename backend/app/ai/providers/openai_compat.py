"""Proveedor OpenAI-compatible (OpenAI, OpenRouter, Ollama, LM Studio...).

Requiere OPENAI_COMPAT_API_KEY. Sin SDK extra: usa httpx (ya instalado).
"""
from __future__ import annotations

import json
import logging

import httpx

from app.ai.providers.base import AIProvider
from app.ai.providers.gemini import _extract_json
from app.ai.providers.gemini import _load_prompt
from app.ai.providers.gemini import _reference_section
from app.config import OPENAI_COMPAT_API_KEY
from app.config import OPENAI_COMPAT_BASE_URL
from app.config import OPENAI_COMPAT_MODEL

logger = logging.getLogger(__name__)


class OpenAICompatProvider(AIProvider):
    name = "openai_compat"

    def available(self) -> bool:
        return bool(OPENAI_COMPAT_API_KEY)

    def _chat(self, system: str, user: str, timeout: int) -> str:
        response = httpx.post(
            f"{OPENAI_COMPAT_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_COMPAT_API_KEY}"},
            json={
                "model": OPENAI_COMPAT_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(f"Respuesta inesperada: {error}")
        if not text or not text.strip():
            raise ValueError("Respuesta vacia del proveedor")
        return text

    def analyze_job(self, job: dict, profile: dict) -> dict:
        from app.config import AI_TIMEOUT_SECONDS

        prompt = _load_prompt("analyze_job.txt").format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            description=(job.get("description", "") or "")[:6000],
            profile_skills=", ".join(
                str(s) for s in (profile.get("skills", []) or [])[:30]
            ),
            target_roles=", ".join(
                str(s) for s in (profile.get("target_roles", []) or [])[:10]
            ),
        )
        return _extract_json(
            self._chat("Responde exclusivamente con JSON valido.",
                       prompt, AI_TIMEOUT_SECONDS)
        )

    def generate_cv_content(
        self, job: dict, analysis: dict, profile: dict,
        reference_cvs: list | None = None,
    ) -> dict:
        from app.config import AI_TIMEOUT_SECONDS

        prompt = _load_prompt("generate_cv.txt").format(
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            job_description=(job.get("description", "") or "")[:6000],
            evidence=", ".join((analysis.get("evidence") or [])[:10]),
            detected_role=analysis.get("detected_role") or "N/A",
            profile_json=json.dumps(profile, ensure_ascii=False)[:8000],
            reference_section=_reference_section(reference_cvs),
        )
        return _extract_json(
            self._chat("Responde exclusivamente con JSON valido.",
                       prompt, AI_TIMEOUT_SECONDS)
        )
