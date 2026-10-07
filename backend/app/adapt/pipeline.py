"""Etapas del pipeline Adaptar-perfil (responsabilidad unica c/u).

`service.adapt_profile_for_job` solo encadena estas etapas y mide
tiempos. Cada etapa recibe datos explicitos y devuelve resultados
explicitos; ninguna lee estado global salvo DB/disco declarados.

Orden: config -> job -> profile -> match -> select -> llm ->
validate -> render -> pdf -> audit(+retry) -> finish.
"""
from __future__ import annotations

import time as _time


class Timings(dict):
    """Acumula duraciones por etapa (segundos, 3 decimales)."""


class _timed:
    def __init__(self, timings: Timings, name: str):
        self._timings = timings
        self._name = name

    def __enter__(self):
        self._t0 = _time.perf_counter()
        return self

    def __exit__(self, *exc):
        self._timings[self._name] = round(
            _time.perf_counter() - self._t0, 3)
        return False


def stage_config(db, uid):
    """pdf_config coercionada + warnings. No toca lo guardado."""
    from app.adapt import content as adapt_content
    from app.services.pdf_config import get_pdf_config_for_renderer

    raw_config = get_pdf_config_for_renderer(db, uid) if uid else {}
    return adapt_content.coerce_pdf_config(raw_config)


def stage_job(db, job_id):
    """Record oferta o AdaptError 404."""
    from app.adapt.service import AdaptError
    from app.services.job_service import get_job_by_id

    try:
        job = get_job_by_id(db=db, job_id=job_id)
    except (TypeError, ValueError) as error:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.",
                         http=404) from error
    if not job:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.", http=404)
    return job


def stage_coerce(profile: dict):
    """Perfil display -> copia tipada (no muta lo guardado)."""
    from app.adapt import content as adapt_content

    return adapt_content.coerce_profile(profile)


def build_offer(job) -> dict:
    """Record oferta -> dict plano de 8 claves para matcher/selector."""
    from app.adapt.service import _as_list

    return {
        "title": job.title or "",
        "company": job.company or "",
        "description": job.description or "",
        "location": job.location or "",
        "modality": getattr(job, "modality", "") or "",
        "requirements": _as_list(getattr(job, "requirements", [])),
        "responsibilities": _as_list(
            getattr(job, "responsibilities", [])),
    }


def stage_profile(db, uid, email):
    """Perfil display del MISMO usuario (+gate de completitud).

    Invitado -> demo; Google -> solo lo suyo. Lanza AdaptError 404/400.
    """
    from app.adapt import guest
    from app.adapt.service import _is_profile_complete, AdaptError
    from app.services.job_service import get_rich_profile_for
    from app.services.search_profiles import _is_guest

    if uid and not _is_guest(uid, email):
        raw = get_rich_profile_for(db, uid, email)
        if not _is_profile_complete(raw):
            raise AdaptError(
                "PROFILE_INCOMPLETE",
                "Debe completar su perfil antes de generar un CV adaptado. "
                "Vaya a la sección de Perfil y complete los campos obligatorios.",
                http=400
            )
        profile = guest.get_profile_for_cv(db, user_id=uid, email=email)
    else:
        profile = guest.get_profile_for_cv(db)
        if guest.profile_is_empty(profile):
            raise AdaptError(
                "PROFILE_NOT_FOUND",
                "Perfil de invitado no disponible.", http=404)
    return profile


def stage_match(offer: dict, profile: dict) -> dict:
    """Matching deterministico (puro, sin IA ni red)."""
    from app.adapt import matcher

    return matcher.match_offer_profile(offer, profile)


def stage_select(profile: dict, offer: dict, matching: dict,
                 pdf_config: dict) -> dict:
    """Seleccion + contacto + titulo. Copias nuevas, no muta entradas."""
    import copy as _copy

    from app.adapt import selector

    content = selector.select_cv_content(
        _copy.deepcopy(profile), offer, matching, pdf_config)
    for key in ("full_name", "title", "email", "phone", "linkedin",
                "github", "portfolio", "location"):
        content[key] = profile.get(key, "")
    if content.get("title_line"):
        content["title"] = content["title_line"]
    return content


def stage_llm(content: dict, matching: dict, pdf_config: dict,
              db, uid, preferred_provider) -> tuple[dict, list, list, dict]:
    """UNA sola via IA: usuario (con fallback) o deterministico.

    Devuelve (content, adaptations, warnings, llm_info). Muta el
    `content` recibido (ya es copia de trabajo del pipeline).
    """
    from app.adapt import llm, rewrite as adapt_rewrite
    from app.ai import user_llm

    llm_info: dict = {"path": "deterministic", "provider": "none"}
    user_client = None
    try:
        user_client = user_llm.for_user(db, uid, preferred_provider)
    except Exception:  # noqa: BLE001
        user_client = None
    if user_client is not None:
        try:
            polished = user_llm.polish_summary_for_user(
                user_client, content.get("summary", ""),
                content.get("target_role", ""),
                matching.get("matched_skills") or [])
            llm_info = {"path": "user",
                        "provider": user_client.provider_used or "user"}
        except Exception:  # noqa: BLE001
            user_client = None
            polished = llm.polish_summary(
                content.get("summary", ""), content.get("target_role", ""),
                matching.get("matched_skills") or [])
    else:
        polished = llm.polish_summary(
            content.get("summary", ""), content.get("target_role", ""),
            matching.get("matched_skills") or [])
    content["summary"] = polished["summary"]
    content["summary_provider"] = polished["provider"]

    adaptations: list[dict] = []
    warnings: list[str] = []
    if pdf_config.get("ai_rewrite_bullets"):
        allowed = list(content.get("skills") or [])
        role = str(content.get("target_role") or "")
        for exp in content.get("experiences") or []:
            if not isinstance(exp, dict):
                continue
            current = [str(b) for b in (exp.get("bullets") or []) if b]
            if not current:
                continue
            if user_client is not None:
                try:
                    result = user_llm.rewrite_bullets_for_user(
                        user_client, current, allowed, role)
                except Exception:  # noqa: BLE001
                    result = adapt_rewrite.rewrite_bullets(
                        current, allowed, role)
            else:
                result = adapt_rewrite.rewrite_bullets(
                    current, allowed, role)
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
            warnings.append(
                f"IA reformulo bullets en {len(adaptations)} experiencia(s) "
                f"(verificado; diff en adapt.json).")
    content["summary"] = polished["summary"]
    content["summary_provider"] = polished["provider"]
    content["adaptations"] = adaptations
    return content, adaptations, warnings, llm_info


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


def stage_validate(content: dict, pre_ia: dict, profile: dict,
                   pdf_config: dict) -> tuple[dict, list[str]]:
    """Pre-render: si falla, conserva el contenido original (pre-IA).

    Tambien calcula `missing` (marcadores de ausencia) sobre el
    contenido final, como antes hacia el orquestador.
    """
    from app.adapt import validate as adapt_validate

    ok, issues = adapt_validate.validate_pre_render(
        content, profile, pdf_config)
    if not ok:
        reverted = pre_ia
        reverted["summary_provider"] = "none"
        reverted["missing"] = _missing_profile_fields(reverted)
        return reverted, [
            "Validacion pre-render fallo (" + "; ".join(issues[:5]) +
            "): se conserva el contenido original sin IA."]
    content["missing"] = _missing_profile_fields(content)
    return content, []


def stage_render(content: dict, offer: dict, pdf_config: dict) -> str:
    """Content -> HTML. Solo formato, sin decisiones de datos."""
    from app.adapt import html_renderer
    from app.adapt.service import AdaptError

    try:
        return html_renderer.render_cv_html(content, offer, pdf_config)
    except ValueError as error:
        raise AdaptError("HTML_FAILED", str(error), http=502) from error


def stage_pdf_paths(job, uid, email):
    """Directorio del owner (creandolo) + ruta del PDF."""
    from pathlib import Path

    from app.adapt.service import adapt_dir

    directory = adapt_dir(job.id, uid, email)
    return directory, Path(directory) / "cv.pdf"


def stage_pdf(html_text: str, directory, filename: str = "cv.pdf"):
    """HTML -> PDF verificado en disco. Solo conversion."""
    from pathlib import Path

    from app.adapt import pdf
    from app.adapt.service import AdaptError

    out = Path(directory) / filename
    try:
        pdf.html_to_pdf(html_text, out)
    except pdf.PdfError as error:
        raise AdaptError(error.code, str(error), http=502) from error
    return out


def stage_audit(content: dict, profile: dict, offer: dict,
                pdf_config: dict, directory, html_text: str):
    """Audita y reintenta UNA vez en compacto si excede paginas.

    Devuelve (audit, warnings_extra, html_final). No recorta
    informacion obligatoria.
    """
    from app.adapt import audit as adapt_audit
    from app.adapt import pdf

    warnings: list[str] = []
    pdf_path = __import__("pathlib").Path(directory) / "cv.pdf"
    (directory / "cv.html").write_text(html_text, encoding="utf-8")
    audit = adapt_audit.audit_cv(
        content, profile, offer, pdf_config, pdf_path)
    try:
        max_pages = int(pdf_config.get("max_pages", 0) or 0)
    except (TypeError, ValueError):
        max_pages = 0
    if max_pages > 0 and audit["facts"]["pages"] > max_pages \
            and not pdf_config.get("compact_mode"):
        from app.adapt import html_renderer

        compact_config = dict(pdf_config, compact_mode=True)
        try:
            retry_html = html_renderer.render_cv_html(
                content, offer, compact_config)
            (directory / "cv.html").write_text(
                retry_html, encoding="utf-8")
            pdf.html_to_pdf(retry_html, pdf_path)
            html_text = retry_html
            audit = adapt_audit.audit_cv(
                content, profile, offer, compact_config, pdf_path)
            warnings.append(
                "Se excedia el maximo de paginas: se regenero en modo "
                "compacto (mismo contenido).")
        except (ValueError, pdf.PdfError):
            pass
    return audit, warnings, html_text


def patch_timings(directory, timings: dict) -> None:
    """Completa `timings` en adapt.json tras medir `finish` (el with
    cierra despues de construir la respuesta). Best-effort."""
    import json as _json
    from pathlib import Path

    path = Path(directory) / "adapt.json"
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    data["timings"] = dict(timings)
    try:
        path.write_text(_json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    except OSError:
        pass


def stage_finish(job, uid, email, matching: dict, content: dict,
                 warnings: list, audit: dict, timings: dict,
                 llm_info: dict) -> dict:
    """Escribe adapt.json y construye la respuesta API (aditivo)."""
    import json as _json
    from datetime import datetime
    from pathlib import Path

    from app.adapt.service import _owner_key, adapt_dir
    from app.services.search_profiles import _is_guest

    directory = adapt_dir(job.id, uid, email)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "adapt.json").write_text(_json.dumps(
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
         "warnings": warnings,
         "audit": audit,
         "timings": dict(timings),
         "llm": llm_info},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "warnings": warnings,
        "audit": audit,
        "timings": dict(timings),
        "job": {"id": job.id, "title": job.title or "",
                "company": job.company or ""},
        "matching": {
            "percentage": matching["percentage"],
            "matched_skills": matching["matched_skills"],
            "missing_skills": matching["missing_skills"],
        },
        "cv": {
            "id": f"job-{job.id}",
            "summary_provider": content.get("summary_provider"),
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
