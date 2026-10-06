"""Orquestador Adaptar-perfil (FASE 8 logica).

Oferta -> perfil invitado -> matching -> seleccion -> (LLM opcional)
-> HTML -> PDF -> disco. Errores controlados con codigo, nunca
trazas crudas.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


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
              email: str | None = None) -> Path:
    from app.config import ADAPT_CVS_DIR

    directory = ADAPT_CVS_DIR / f"job_{job_id}" / _owner_key(uid, email)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def legacy_adapt_dir(job_id) -> Path:
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
                          email: str | None = None) -> dict:
    """Ejecuta el flujo completo y devuelve la respuesta de la API."""
    from app.adapt import guest, html_renderer, llm, matcher, pdf, selector
    from app.services.job_service import get_job_by_id
    from app.services.search_profiles import _is_guest

    # Config de PDF del usuario (Fase 2: servicio dual SQLite/Firestore).
    # Sin UID o sin fila -> {} y el renderer usa sus defaults.
    # Coercion de tipos exactos del renderer (no toca lo guardado).
    from app.adapt import content as adapt_content
    from app.services.pdf_config import get_pdf_config_for_renderer

    raw_config = get_pdf_config_for_renderer(db, uid) if uid else {}
    pdf_config, config_warnings = adapt_content.coerce_pdf_config(
        raw_config)

    try:
        job = get_job_by_id(db=db, job_id=job_id)
    except (TypeError, ValueError) as error:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.",
                         http=404) from error
    if not job:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.", http=404)

    # Perfil SIEMPRE en forma display (plano+estructurado del MISMO
    # usuario): invitado (sin uid o anonimo sin email) -> demo;
    # Google (uid + email) -> solo lo suyo. Asi el PDF nunca mezcla
    # ni inventa: todo sale de la seccion Perfil.
    if uid and not _is_guest(uid, email):
        from app.services.job_service import get_rich_profile_for
        raw = get_rich_profile_for(db, uid, email)
        # Verificar que el perfil tenga datos mínimos requeridos
        if not _is_profile_complete(raw):
            raise AdaptError(
                "PROFILE_INCOMPLETE",
                "Debe completar su perfil antes de generar un CV adaptado. "
                "Vaya a la sección de Perfil y complete los campos obligatorios.",
                http=400
            )
        profile = guest.get_profile_for_cv(db, user_id=uid, email=email)
    else:
        # Usuario invitado: usar perfil demo
        profile = guest.get_profile_for_cv(db)
        if guest.profile_is_empty(profile):
            raise AdaptError(
            "PROFILE_NOT_FOUND",
            "Perfil de invitado no disponible.", http=404)

    # Frontera tipada: copias coercionadas para matcher/selector/
    # renderer. Lo guardado en Perfil no se modifica aqui.
    profile, profile_warnings = adapt_content.coerce_profile(profile)
    adapt_warnings = list(config_warnings) + list(profile_warnings)

    offer = {
        "title": job.title or "",
        "company": job.company or "",
        "description": job.description or "",
        "location": job.location or "",
        "modality": getattr(job, "modality", "") or "",
        "requirements": _as_list(getattr(job, "requirements", [])),
        "responsibilities": _as_list(
            getattr(job, "responsibilities", [])),
    }
    if not offer["title"] and not offer["description"]:
        raise AdaptError(
            "JOB_INCOMPLETE", "La oferta no tiene datos suficientes.",
            http=400)

    matching = matcher.match_offer_profile(offer, profile)
    # La config manda: topes del usuario sobre la relevancia.
    content = selector.select_cv_content(
        profile, offer, matching, pdf_config)

    polished = llm.polish_summary(
        content.get("summary", ""), content.get("target_role", ""),
        matching.get("matched_skills") or [])
    content["summary"] = polished["summary"]
    content["summary_provider"] = polished["provider"]

    # Datos de contacto para la cabecera (vienen del perfil, no del job).
    for key in ("full_name", "title", "email", "phone", "linkedin",
                "github", "portfolio", "location"):
        content[key] = profile.get(key, "")
    # Titulo compuesto oferta<->perfil (solo con evidencia real).
    if content.get("title_line"):
        content["title"] = content["title_line"]

    # Reformulacion opt-in con LLM supervisado: reordena/enfatiza
    # bullets por experiencia. Verificada termino a termino o se
    # conservan los originales. El diff queda en adapt.json.
    adaptations: list[dict] = []
    if pdf_config.get("ai_rewrite_bullets"):
        from app.adapt import rewrite as adapt_rewrite

        allowed = list(content.get("skills") or [])
        role = str(content.get("target_role") or "")
        for exp in content.get("experiences") or []:
            if not isinstance(exp, dict):
                continue
            current = [str(b) for b in (exp.get("bullets") or []) if b]
            if not current:
                continue
            result = adapt_rewrite.rewrite_bullets(current, allowed, role)
            if result["bullets"] != current:
                adaptations.append({
                    "experience": str(exp.get("title") or ""),
                    "original": current,
                    "adapted": result["bullets"],
                    "provider": result["provider"],
                    "verified": result["verified"],
                    "note": result["note"],
                })
            exp["bullets"] = result["bullets"]
        if adaptations:
            adapt_warnings = list(adapt_warnings) + [
                f"IA reformulo bullets en {len(adaptations)} experiencia(s) "
                f"(verificado; diff en adapt.json)."]
    content["adaptations"] = adaptations

    # Lo que falte IMPORTANTE no se inventa: se marca en el PDF con
    # "(falta información de ...)" en el mismo pedazo (ver renderer).
    content["missing"] = _missing_profile_fields(content)

    try:
        html_text = html_renderer.render_cv_html(content, offer, pdf_config)
    except ValueError as error:
        raise AdaptError("HTML_FAILED", str(error), http=502) from error

    directory = adapt_dir(job.id, uid, email)
    (directory / "cv.html").write_text(html_text, encoding="utf-8")
    try:
        # timeout_ms es milisegundos (int); pdf_config NO va aqui
        # (bug historico: pasarlo como 3er arg rompia con int(dict)).
        pdf.html_to_pdf(html_text, directory / "cv.pdf")
    except pdf.PdfError as error:
        raise AdaptError(error.code, str(error), http=502) from error

    # Auditoria config-driven (no modifica datos, solo reporta).
    from app.adapt import audit as adapt_audit

    audit = adapt_audit.audit_cv(
        content, profile, offer, pdf_config, directory / "cv.pdf")
    # Unico reintento permitido: si excede max_pages y el compacto esta
    # apagado, regenerar compacto (mismo contenido, CSS denso). Jamas
    # recorta informacion obligatoria por configuracion.
    try:
        max_pages = int(pdf_config.get("max_pages", 0) or 0)
    except (TypeError, ValueError):
        max_pages = 0
    if max_pages > 0 and audit["facts"]["pages"] > max_pages \
            and not pdf_config.get("compact_mode"):
        compact_config = dict(pdf_config, compact_mode=True)
        try:
            retry_html = html_renderer.render_cv_html(
                content, offer, compact_config)
            (directory / "cv.html").write_text(
                retry_html, encoding="utf-8")
            pdf.html_to_pdf(retry_html, directory / "cv.pdf")
            html_text = retry_html
            audit = adapt_audit.audit_cv(
                content, profile, offer, compact_config,
                directory / "cv.pdf")
            adapt_warnings = list(adapt_warnings) + [
                "Se excedia el maximo de paginas: se regenero en modo "
                "compacto (mismo contenido)."]
        except (ValueError, pdf.PdfError):
            pass

    (directory / "adapt.json").write_text(json.dumps(
        {"job_id": job.id,
         "created_at": datetime.utcnow().isoformat(),
         "profile_source": "user" if (uid and not _is_guest(uid, email))
         else "guest",
         "owner_uid": _owner_key(uid, email),
         "matching": {k: v for k, v in matching.items()
                      if k in ("percentage", "matched_skills",
                               "missing_skills", "modality_ok",
                               "location_ok", "target_roles_matched",
                               "years_experience")},
         "content": content,
         "warnings": adapt_warnings,
         "audit": audit},
        ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "warnings": adapt_warnings,
        "audit": audit,
        "job": {"id": job.id, "title": job.title or "",
                "company": job.company or ""},
        "matching": {
            "percentage": matching["percentage"],
            "matched_skills": matching["matched_skills"],
            "missing_skills": matching["missing_skills"],
        },
        "cv": {
            "id": f"job-{job.id}",
            "summary_provider": polished["provider"],
            "experiences": [
                {"title": e.get("title") or e.get("name") or "",
                 "company": e.get("company") or e.get("institution") or ""}
                for e in content["experiences"]],
            "projects": [p.get("name") or p.get("title") or ""
                         for p in content["projects"]],
            "education": [
                {"degree": e.get("degree") or e.get("title") or "",
                 "institution": e.get("institution") or ""}
                for e in content["education"]],
            "languages": [
                {"label": l.get("label") or l.get("language_label") or l.get("language") or "",
                 "level": l.get("level") or ""}
                for l in content["languages"]],
            "skills_groups": content["skills_groups"],
            "skills_soft": content["skills_soft"],
            "other_studies": content["other_studies"],
            "other_knowledge": content["other_knowledge"],
            "projects": [p.get("name") or p.get("title") or ""
                         for p in content["projects"]],
            "download_url": f"/jobs/{job.id}/adapt-cv/download?format=pdf",
            "preview_url": f"/jobs/{job.id}/adapt-cv/download?format=pdf",
        },
    }


def error_body(error: AdaptError) -> dict:
    return {"success": False,
            "error": {"code": error.code, "message": str(error)}}


def _missing_profile_fields(content: dict) -> list[str]:
    """Campos importantes ausentes en el perfil (sin inventar: el
    renderer los muestra como '(falta información de ...)')."""
    missing: list[str] = []

    def blank(value) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False

    if blank(content.get("title")):
        missing.append("title")
    if blank(content.get("email")):
        missing.append("email")
    if blank(content.get("phone")):
        missing.append("phone")
    if blank(content.get("summary")):
        missing.append("summary")
    skills = list(content.get("skills") or [])
    groups = content.get("skills_groups") or {}
    if not skills and not any(groups.get(k) for k in groups):
        missing.append("skills")
    if blank(content.get("experiences")):
        missing.append("experiences")
    if blank(content.get("education")):
        missing.append("education")
    return missing


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
