"""Orquestador Adaptar-perfil (FASE 8 logica).

Oferta -> perfil invitado -> matching -> seleccion -> (LLM opcional)
-> HTML -> PDF -> disco. Errores controlados con codigo, nunca
trazas crudas.

Orquestador DELGADO: cada etapa vive en `adapt/pipeline.py` con
responsabilidad unica; aqui solo se encadenan y se miden tiempos.
"""
from __future__ import annotations

import json


class AdaptError(RuntimeError):
    def __init__(self, code: str, message: str, http: int = 502):
        super().__init__(message)
        self.code = code
        self.http = http


def _owner_key(uid: str | None, email: str | None = None) -> str:
    """Subdirectorio por usuario: cada sesion tiene sus PDFs.

    Invitado (sin uid o anonimo sin email) comparte "guest" porque
    comparte los mismos datos demo. Google usa su uid.
    """
    import re as _re

    from app.services.search_profiles import _is_guest

    if not uid or _is_guest(uid, email):
        return "guest"
    safe = _re.sub(r"[^A-Za-z0-9_-]", "_", str(uid))[:64]
    return safe or "guest"


def adapt_dir(job_id, uid: str | None = None,
              email: str | None = None):
    from app.config import ADAPT_CVS_DIR

    directory = ADAPT_CVS_DIR / f"job_{job_id}" / _owner_key(uid, email)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def legacy_adapt_dir(job_id):
    """Ubicacion anterior (sin subdirectorio): solo lectura para
    migrar descargas generadas antes del aislamiento por usuario."""
    from app.config import ADAPT_CVS_DIR

    return ADAPT_CVS_DIR / f"job_{job_id}"


def _as_list(value) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except ValueError:
            return []
    return []


def adapt_profile_for_job(db, job_id, uid: str | None = None,
                          email: str | None = None,
                          preferred_provider: str | None = None) -> dict:
    """Ejecuta el flujo completo y devuelve la respuesta de la API.

    `preferred_provider` (id de proveedor del usuario o None=auto):
    la IA del CV consume SOLO keys del usuario con fallback
    automatico; sin keys, flujo deterministico local (sin globales).
    """
    import copy as _copy

    from app.adapt import pipeline as stages

    timings: stages.Timings = stages.Timings()

    with stages._timed(timings, "config"):
        pdf_config, config_warnings = stages.stage_config(db, uid)
    with stages._timed(timings, "job"):
        job = stages.stage_job(db, job_id)
    with stages._timed(timings, "profile"):
        profile = stages.stage_profile(db, uid, email)
    with stages._timed(timings, "coerce"):
        profile, profile_warnings = stages.stage_coerce(profile)
    adapt_warnings = list(config_warnings) + list(profile_warnings)

    offer = stages.build_offer(job)
    if not offer["title"] and not offer["description"]:
        raise AdaptError(
            "JOB_INCOMPLETE", "La oferta no tiene datos suficientes.",
            http=400)
    with stages._timed(timings, "match"):
        matching = stages.stage_match(offer, profile)
    with stages._timed(timings, "select"):
        content = stages.stage_select(profile, offer, matching, pdf_config)
    # Snapshot pre-IA: si la validacion posterior falla, se conserva
    # este contenido original en vez de generar no verificado.
    pre_ia_content = _copy.deepcopy(content)

    with stages._timed(timings, "llm"):
        content, adaptations, llm_warnings, llm_info = stages.stage_llm(
            content, matching, pdf_config, db, uid, preferred_provider,
            offer)
    adapt_warnings = list(adapt_warnings) + list(llm_warnings)

    with stages._timed(timings, "validate"):
        content, validation_warnings = stages.stage_validate(
            content, pre_ia_content, profile, pdf_config)
    adapt_warnings = list(adapt_warnings) + list(validation_warnings)

    with stages._timed(timings, "render"):
        html_text = stages.stage_render(content, offer, pdf_config)
    with stages._timed(timings, "pdf"):
        directory, _pdf_path = stages.stage_pdf_paths(
            job, uid, email)
        stages.stage_pdf(html_text, directory)

    with stages._timed(timings, "audit"):
        audit, audit_warnings, html_text = stages.stage_audit(
            content, profile, offer, pdf_config, directory, html_text)
    adapt_warnings = list(adapt_warnings) + list(audit_warnings)

    # Puerta de entrega: con errores bloqueantes NO se marca done ni
    # se entrega como CV valido.
    from app.adapt.audit import blocking_issues as _blocking

    _blocking_issues = _blocking(audit)
    if _blocking_issues:
        raise AdaptError(
            "AUDIT_FAILED",
            "Auditoria bloqueo la entrega: " +
            "; ".join(i["message"] for i in _blocking_issues[:3]),
            http=502)

    with stages._timed(timings, "finish"):
        result = stages.stage_finish(
            job, uid, email, matching, content, adapt_warnings, audit,
            timings, llm_info)
    result["timings"] = dict(timings)
    stages.patch_timings(
        stages.stage_pdf_paths(job, uid, email)[0], timings)
    return result


def error_body(error: AdaptError) -> dict:
    return {"success": False,
            "error": {"code": error.code, "message": str(error)}}


def _is_profile_complete(profile: dict) -> bool:
    """Verifica si el perfil tiene los campos mínimos requeridos.

    Vale lo guardado en el tab simple (plano, en "_flat") o en el
    estructurado (personal): el usuario puede completar cualquiera.
    """
    if not profile:
        return False

    # Campos obligatorios: nombre completo, email, teléfono
    personal = profile.get("personal") or {}
    flat = profile.get("_flat") or {}
    full_name = (
        personal.get("full_name") or flat.get("full_name") or "").strip()
    email = (personal.get("email") or flat.get("email") or "").strip()
    phone = (personal.get("phone") or flat.get("phone") or "").strip()

    if not full_name or not email or not phone:
        return False

    # Al menos una experiencia o educación
    experiences = profile.get("experiences") or profile.get("experience") or []
    education = profile.get("education") or []
    if not experiences and not education:
        return False

    return True
