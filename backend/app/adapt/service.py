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


def adapt_dir(job_id) -> Path:
    from app.config import ADAPT_CVS_DIR

    directory = ADAPT_CVS_DIR / f"job_{job_id}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


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


def adapt_profile_for_job(db, job_id, uid: str | None = None) -> dict:
    """Ejecuta el flujo completo y devuelve la respuesta de la API."""
    from app.adapt import guest, html_renderer, llm, matcher, pdf, selector
    from app.services.job_service import get_job_by_id

    # Obtener configuración de PDF del usuario (si hay UID)
    pdf_config = {}
    if uid:
        from app.database.models import PDFConfig
        pdf_cfg = db.query(PDFConfig).filter(PDFConfig.uid == uid).first()
        if pdf_cfg:
            import json as _json
            pdf_config = {
                "font_family": pdf_cfg.font_family,
                "font_size_pt": pdf_cfg.font_size_pt,
                "section_order": _json.loads(pdf_cfg.section_order) if pdf_cfg.section_order else [],
                "date_format": pdf_cfg.date_format,
                "show_skill_chips": bool(pdf_cfg.show_skill_chips),
                "compact_mode": bool(pdf_cfg.compact_mode),
                "header_style": pdf_cfg.header_style,
                "section_divider": pdf_cfg.section_divider,
                "margin_top_mm": pdf_cfg.margin_top_mm,
                "margin_bottom_mm": pdf_cfg.margin_bottom_mm,
                "margin_left_mm": pdf_cfg.margin_left_mm,
                "margin_right_mm": pdf_cfg.margin_right_mm,
                "section_spacing_pt": pdf_cfg.section_spacing_pt,
                "accent_color": pdf_cfg.accent_color,
            }

    try:
        job = get_job_by_id(db=db, job_id=job_id)
    except (TypeError, ValueError) as error:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.",
                         http=404) from error
    if not job:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.", http=404)

    # Si hay UID (usuario autenticado), verificar que tenga perfil completo
    if uid:
        from app.services.job_service import get_rich_profile_for
        profile = get_rich_profile_for(db, uid, "")
        # Verificar que el perfil tenga datos mínimos requeridos
        if not _is_profile_complete(profile):
            raise AdaptError(
                "PROFILE_INCOMPLETE",
                "Debe completar su perfil antes de generar un CV adaptado. "
                "Vaya a la sección de Perfil y complete los campos obligatorios.",
                http=400
            )
    else:
        # Usuario invitado: usar perfil demo
        profile = guest.get_profile_for_cv(db)
        if guest.profile_is_empty(profile):
            raise AdaptError(
            "PROFILE_NOT_FOUND",
            "Perfil de invitado no disponible.", http=404)

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
    content = selector.select_cv_content(profile, offer, matching)

    polished = llm.polish_summary(
        content.get("summary", ""), content.get("target_role", ""),
        matching.get("matched_skills") or [])
    content["summary"] = polished["summary"]
    content["summary_provider"] = polished["provider"]

    # Datos de contacto para la cabecera (vienen del perfil, no del job).
    for key in ("full_name", "title", "email", "phone", "linkedin",
                "github", "portfolio", "location"):
        content[key] = profile.get(key, "")

    try:
        html_text = html_renderer.render_cv_html(content, offer, pdf_config)
    except ValueError as error:
        raise AdaptError("HTML_FAILED", str(error), http=502) from error

    directory = adapt_dir(job.id)
    (directory / "adapt.json").write_text(json.dumps(
        {"job_id": job.id,
         "created_at": datetime.utcnow().isoformat(),
         "profile_source": "guest",
         "matching": {k: v for k, v in matching.items()
                      if k in ("percentage", "matched_skills",
                               "missing_skills", "modality_ok",
                               "location_ok", "target_roles_matched",
                               "years_experience")},
         "content": content},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "cv.html").write_text(html_text, encoding="utf-8")
    try:
        pdf.html_to_pdf(html_text, directory / "cv.pdf", pdf_config)
    except pdf.PdfError as error:
        raise AdaptError(error.code, str(error), http=502) from error

    return {
        "success": True,
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


def _is_profile_complete(profile: dict) -> bool:
    """Verifica si el perfil tiene los campos mínimos requeridos."""
    if not profile:
        return False
    
    # Campos obligatorios: nombre completo, email, teléfono
    personal = profile.get("personal") or {}
    full_name = (personal.get("full_name") or "").strip()
    email = (personal.get("email") or "").strip()
    phone = (personal.get("phone") or "").strip()
    
    if not full_name or not email or not phone:
        return False
    
    # Al menos una experiencia o educación
    experiences = profile.get("experiences") or profile.get("experience") or []
    education = profile.get("education") or []
    if not experiences and not education:
        return False
    
    return True
