"""LLM con cuota del usuario para generacion de CV (nunca global).

Flujo: proveedor elegido (o primero disponible) -> fallback automatico
ante cuota/rate/no-disponible -> si nadie responde, el llamador usa su
fallback deterministico local. Cada intento registra estado por usuario.

Las tareas del SISTEMA (scoring/analisis via AIRouter global) no pasan
por aqui y no se tocan.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class UserLLMError(Exception):
    """Ningun proveedor del usuario respondio."""

    def __init__(self, message: str, attempts: list[dict] | None = None):
        super().__init__(message)
        self.attempts = attempts or []


class UserLLM:
    """Cliente con las keys de un usuario. `provider_used` informa."""

    def __init__(self, db, uid: str, preferred: str | None = None):
        from app.ai import user_providers as providers

        if preferred is not None:
            providers.get_spec(preferred)  # ValueError si no existe
        self._db = db
        self._uid = uid
        self._preferred = preferred
        self.provider_used: str | None = None

    def _ordered(self) -> list[str]:
        from app.services import ai_keys

        configured = ai_keys.configured_providers(self._db, self._uid)
        if self._preferred:
            if self._preferred not in configured:
                raise UserLLMError(
                    f"Proveedor '{self._preferred}' sin key configurada.")
            rest = [p for p in configured if p != self._preferred]
            return [self._preferred, *rest]
        return configured

    def generate(self, system: str, user: str) -> str:
        """Texto del primer proveedor que responda (con fallback)."""
        from app.ai import user_providers as providers
        from app.config import AI_TIMEOUT_SECONDS
        from app.services import ai_keys

        ordered = self._ordered()
        if not ordered:
            raise UserLLMError("Sin proveedores configurados.")
        attempts: list[dict] = []
        for pid in ordered:
            key = ai_keys.get_key(self._db, self._uid, pid)
            if not key:
                continue
            try:
                text = providers.SUPPORTED[pid].complete(
                    system, user, key, AI_TIMEOUT_SECONDS)
                ai_keys.record_result(self._db, self._uid, pid, True)
                self.provider_used = pid
                return text
            except providers.ProviderError as error:
                ai_keys.record_result(
                    self._db, self._uid, pid, False,
                    error.code, str(error)[:200])
                attempts.append({"provider": pid, "code": error.code})
                logger.warning("LLM usuario %s fallo: %s",
                               pid, str(error)[:200])
                continue
            except Exception as error:  # noqa: BLE001
                ai_keys.record_result(
                    self._db, self._uid, pid, False,
                    "unknown", str(error)[:200])
                attempts.append({"provider": pid, "code": "unknown"})
                continue
        raise UserLLMError(
            "Ningun proveedor disponible: " + ", ".join(
                f"{a['provider']}({a['code']})" for a in attempts),
            attempts)

    def has_providers(self) -> bool:
        try:
            return bool(self._ordered())
        except UserLLMError:
            return False


def for_user(db, uid: str | None,
             preferred: str | None = None) -> UserLLM | None:
    """None si el usuario no tiene keys (flujo deterministico local)."""
    if not uid:
        return None
    try:
        client = UserLLM(db, uid, preferred)
    except ValueError:
        return None
    if preferred and not client.has_providers():
        return None
    return client if client.has_providers() else None


def polish_summary_for_user(client: UserLLM, original: str,
                            target_role: str,
                            matched_skills: list[str]) -> dict:
    """Pulido con cuota del usuario. Verificado por longitud."""
    from app.ai.providers.gemini import _extract_json

    original = str(original or "").strip()
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
    raw = client.generate(
        "Responde exclusivamente con JSON valido.", prompt)
    parsed = _extract_json(raw)
    summary = str(parsed.get("summary") or "").strip()
    if not (30 <= len(summary) <= 600):
        raise ValueError("Resumen pulido fuera de rango")
    return {"summary": summary,
            "provider": client.provider_used or "user"}


def rewrite_bullets_for_user(client: UserLLM, bullets: list[str],
                             allowed_skills: list[str],
                             target_role: str) -> dict:
    """Reescritura supervisada con cuota del usuario (verificada)."""
    from app.adapt.rewrite import verify_rewrite
    from app.ai.providers.gemini import _extract_json

    originals = [str(b or "").strip() for b in bullets or []]
    originals = [b for b in originals if b]
    if not originals:
        return {"bullets": [], "provider": client.provider_used or "user",
                "verified": True, "note": "sin bullets"}
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
    raw = client.generate(
        "Responde exclusivamente con JSON valido.", prompt)
    parsed = _extract_json(raw)
    rewritten = parsed.get("bullets") if isinstance(parsed, dict) else None
    if not isinstance(rewritten, list):
        raise ValueError("sin lista de bullets")
    rewritten = [str(b or "").strip()[:280] for b in rewritten]
    rewritten = [b for b in rewritten if b]
    ok, reason = verify_rewrite(originals, rewritten)
    if not ok:
        raise ValueError(f"verificacion fallo ({reason})")
    return {"bullets": rewritten,
            "provider": client.provider_used or "user",
            "verified": True, "note": "reformulado y verificado"}


def generate_cv_content_for_user(client: UserLLM, job: dict, analysis: dict,
                                 profile: dict,
                                 reference_cvs: list | None = None) -> dict:
    """CVContent via proveedor del usuario (flujo legacy sin globales)."""
    import json as _json

    from app.ai.providers.gemini import _extract_json, _load_prompt
    from app.ai.providers.gemini import _reference_section
    from app.ai.schemas.cv_content import CVContent

    prompt = _load_prompt("generate_cv.txt").format(
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        job_description=(job.get("description", "") or "")[:6000],
        evidence=", ".join((analysis.get("evidence") or [])[:10]),
        detected_role=analysis.get("detected_role") or "N/A",
        profile_json=_json.dumps(profile, ensure_ascii=False)[:8000],
        reference_section=_reference_section(reference_cvs),
    )
    raw = client.generate(
        "Responde exclusivamente con JSON valido.", prompt)
    validated = CVContent.model_validate(_extract_json(raw))
    return {"provider": client.provider_used or "user",
            **validated.model_dump()}
