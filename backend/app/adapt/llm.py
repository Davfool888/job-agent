"""Pulido opcional del resumen con LLM (FASE 5).

Apagado por defecto: el flujo funciona 100% sin LLM. Solo se activa
con ADAPT_LLM_ENABLED=true y un proveedor real disponible (gemini u
openai_compat). Jamas genera el CV: solo reescribe el resumen con los
mismos hechos. Ante cualquier fallo devuelve el original.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def llm_available() -> bool:
    from app.config import ADAPT_LLM_ENABLED

    if not ADAPT_LLM_ENABLED:
        return False
    try:
        from app.ai.providers.gemini import GeminiProvider
        from app.ai.providers.openai_compat import OpenAICompatProvider

        return GeminiProvider().available() or OpenAICompatProvider(
        ).available()
    except Exception:  # noqa: BLE001
        return False


def polish_summary(
    original: str, target_role: str, matched_skills: list[str]
) -> dict:
    """Devuelve {"summary": ..., "provider": ...}. Sin LLM: el original."""
    original = str(original or "").strip()
    if not llm_available():
        return {"summary": original, "provider": "none"}
    try:
        return {"summary": _polish_with_gemini(
            original, target_role, matched_skills), "provider": "gemini"}
    except Exception as error:  # noqa: BLE001
        logger.warning("Pulido LLM fallo, uso original: %s", error)
        return {"summary": original, "provider": "none"}


def _polish_with_gemini(
    original: str, target_role: str, matched_skills: list[str]
) -> str:
    from app.ai.providers.gemini import GeminiProvider, _extract_json
    from app.config import AI_TIMEOUT_SECONDS

    provider = GeminiProvider()
    if not provider.available():
        raise RuntimeError("Gemini no disponible para pulido")
    prompt = (
        "Reescribe este resumen profesional en 2-3 lineas adaptadas al "
        "cargo objetivo, usando UNICAMENTE los hechos del texto original. "
        "PROHIBIDO inventar experiencia, tecnologias, empresas, fechas o "
        "habilidades; prohibido agregar skills fuera de la lista dada. "
        "Responde SOLO JSON {\"summary\": \"...\"}.\n\n"
        f"CARGO: {target_role[:120]}\n"
        f"SKILLS PERMITIDAS: {', '.join(matched_skills[:12])}\n"
        f"ORIGINAL: {original[:1500]}"
    )
    # Nota: solo Gemini implementa pulido; si no esta disponible se
    # usa el original (ver polish_summary).
    raw = provider._generate(prompt, AI_TIMEOUT_SECONDS)
    parsed = _extract_json(raw)
    summary = str(parsed.get("summary") or "").strip()
    if not (30 <= len(summary) <= 600):
        raise ValueError("Resumen pulido fuera de rango")
    return summary
