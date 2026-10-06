"""Reformulacion de bullets con LLM supervisado (opt-in).

Limite consciente resuelto con tres seguros:
1. Opt-in: solo corre si el usuario lo activa (`ai_rewrite_bullets`)
   Y hay proveedor disponible. Apagado = flujo deterministico actual.
2. Prompt cerrado: reordenar/enfatizar con los hechos dados;
   prohibido agregar tecnologias, metricas, empresas o fechas.
3. Verificacion deterministica posterior: cada termino tecnico y
   cada numero del resultado debe existir en el original. Si algo
   falla, se conservan los bullets originales y se reporta.

Nunca modifica el perfil guardado: solo la copia del CV en curso.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def rewrite_available() -> bool:
    """Puerta opt-in: flag de config global no aplica aqui (es por
    usuario via pdf_config); esto solo chequea motor disponible."""
    from app.adapt.llm import llm_available

    return llm_available()


def _numbers(text: str) -> set[str]:
    import re as _re

    return set(_re.findall(r"\d[\d.,]*%?", str(text or "")))


def _tech_terms(text: str) -> set[str]:
    """Terminos del vocabulario presentes (normalizados).

    Vocabulario del matcher + extras solo-verificacion (lenguajes
    que el matcher no trae para no alterar el scoring existente).
    """
    from app.adapt.matcher import _vocab
    from app.analysis.signals import norm, phrases_found

    found: set[str] = set()
    text_norm = norm(text)
    for label, aliases in _vocab():
        if phrases_found(text_norm, [label, *aliases]):
            found.add(norm(label))
    for extra in ("rust", "kotlin", "swift", "scala", "ruby", "php",
                  "perl", "cobol", "vba", "dart", "flutter", "laravel",
                  "haskell", "elixir", "golang", "tensorflow", "pytorch",
                  "redis", "graphql", "selenium"):
        if phrases_found(text_norm, [extra]):
            found.add(extra)
    import re as _re

    if _re.search(r"(?<![a-z])go(?![a-z])", text_norm):
        found.add("go")
    return found


def verify_rewrite(originals: list[str], rewritten: list[str]) -> tuple[bool, str]:
    """Todo numero y tech del rewrite existe en el original."""
    src_text = " ".join(originals)
    out_text = " ".join(rewritten)
    if not rewritten or len(rewritten) != len(originals):
        return False, "conteo distinto de bullets"
    for number in _numbers(out_text):
        if number not in _numbers(src_text):
            return False, f"metrica nueva: {number}"
    src_terms = _tech_terms(src_text)
    for term in _tech_terms(out_text):
        if term not in src_terms:
            return False, f"tecnologia nueva: {term}"
    if len(out_text) > len(src_text) * 2:
        return False, "texto mas del doble de largo"
    return True, ""


def rewrite_bullets(bullets: list[str], allowed_skills: list[str],
                    target_role: str) -> dict:
    """Reordena/enfatiza bullets con Gemini. Siempre verificado.

    Devuelve {"bullets", "provider", "verified", "note"}. Ante
    cualquier duda devuelve los originales.
    """
    originals = [str(b or "").strip() for b in bullets or []]
    originals = [b for b in originals if b]
    if not originals:
        return {"bullets": [], "provider": "none",
                "verified": True, "note": "sin bullets"}
    if not rewrite_available():
        return {"bullets": originals, "provider": "none",
                "verified": True, "note": "LLM no disponible"}
    try:
        from app.ai.providers.gemini import GeminiProvider, _extract_json
        from app.config import AI_TIMEOUT_SECONDS

        provider = GeminiProvider()
        if not provider.available():
            raise RuntimeError("Gemini no disponible")
        prompt = (
            "Reescribe estos bullets de experiencia para el cargo "
            f"'{target_role[:80]}'. REGLAS ESTRICTAS: conserva todos los "
            "hechos, numeros, empresas y fechas; NO agregues tecnologias, "
            "metricas, resultados ni responsabilidades nuevas; solo "
            "reordena y enfatiza lo relevante usando estas skills "
            "permitidas: "
            f"{', '.join(allowed_skills[:15])}. Mismo numero de bullets, "
            "cada uno maximo 220 caracteres. Responde SOLO JSON "
            '{"bullets": ["..."]}.\n\nBULLETS:\n'
            + "\n".join(f"- {b[:400]}" for b in originals[:6])
        )
        parsed = _extract_json(provider._generate(prompt, AI_TIMEOUT_SECONDS))
        rewritten = parsed.get("bullets") if isinstance(parsed, dict) else None
        if not isinstance(rewritten, list):
            raise ValueError("sin lista de bullets")
        rewritten = [str(b or "").strip()[:280] for b in rewritten]
        rewritten = [b for b in rewritten if b]
        ok, reason = verify_rewrite(originals, rewritten)
        if not ok:
            logger.warning("Rewrite rechazado (%s), uso original.", reason)
            return {"bullets": originals, "provider": "gemini",
                    "verified": False,
                    "note": f"verificacion fallo ({reason}): original"}
        return {"bullets": rewritten, "provider": "gemini",
                "verified": True, "note": "reformulado y verificado"}
    except Exception as error:  # noqa: BLE001
        logger.warning("Rewrite fallo (%s), uso original.", error)
        return {"bullets": originals, "provider": "none",
                "verified": True, "note": "fallo LLM: original"}
