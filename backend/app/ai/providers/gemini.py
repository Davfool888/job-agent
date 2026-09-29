"""Proveedor Gemini (API oficial google-genai). Requiere GEMINI_API_KEY."""
from __future__ import annotations

import json
import logging
import re

from app.ai.providers.base import AIProvider
from app.config import GEMINI_API_KEY
from app.config import GEMINI_MODEL

logger = logging.getLogger(__name__)


def _load_prompt(name: str) -> str:
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "prompts" / name
    return path.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Extrae el primer objeto JSON (tolera fences ```json)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Sin objeto JSON en la respuesta")
    return json.loads(cleaned[start : end + 1])


class GeminiProvider(AIProvider):
    name = "gemini"

    def available(self) -> bool:
        if not GEMINI_API_KEY:
            return False
        try:
            import google.genai  # noqa: F401
            return True
        except ImportError:
            return False

    def _generate(self, prompt: str, timeout: int) -> str:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "http_options": {"timeout": timeout * 1000},
            },
        )
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Respuesta vacia de Gemini")
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
        return _extract_json(self._generate(prompt, AI_TIMEOUT_SECONDS))

    def generate_cv_content(
        self, job: dict, analysis: dict, profile: dict
    ) -> dict:
        from app.config import AI_TIMEOUT_SECONDS

        prompt = _load_prompt("generate_cv.txt").format(
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            job_description=(job.get("description", "") or "")[:6000],
            evidence=", ".join((analysis.get("evidence") or [])[:10]),
            detected_role=analysis.get("detected_role") or "N/A",
            profile_json=json.dumps(profile, ensure_ascii=False)[:8000],
        )
        return _extract_json(self._generate(prompt, AI_TIMEOUT_SECONDS))
