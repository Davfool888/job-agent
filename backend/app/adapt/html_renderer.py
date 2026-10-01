"""Render HTML del CV (FASE 6).

Plantilla reutilizable (templates/cv.html + cv.css) + datos
escapados. FASE 14: todo dato de perfil/oferta pasa por html.escape;
la plantilla no ejecuta JavaScript (Chromium con JS apagado).
"""
from __future__ import annotations

import html
from pathlib import Path


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _chips(items: list) -> str:
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    if not items:
        return ""
    return '<div class="chips">' + "".join(
        f'<span class="chip">{esc(i)}</span>' for i in items) + "</div>"


def _contact_line(content: dict) -> str:
    parts = [content.get("email"), content.get("phone"),
             content.get("location"), content.get("linkedin"),
             content.get("github"), content.get("portfolio")]
    return " · ".join(esc(p) for p in parts if str(p).strip())


def _section(title: str, inner: str) -> str:
    if not inner.strip():
        return ""
    return f"<section><h2>{esc(title)}</h2>{inner}</section>"


def _experience(items: list) -> str:
    blocks = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        meta = " · ".join(p for p in [
            item.get("title"), item.get("city"), item.get("modality"),
            " / ".join(p for p in [item.get("start"), item.get("end")]
                       if p) or ("Actualidad" if item.get("is_current")
                                 else ""),
        ] if p)
        blocks.append(
            '<div class="item">'
            f'<div class="item-head"><strong>{esc(item.get("company"))}'
            f"</strong></div>"
            f'<div class="item-meta">{esc(meta)}</div>'
            + (f'<p class="desc">{esc(item.get("description"))}</p>'
               if item.get("description") else "")
            + _chips(list(item.get("technical_skills") or []) + list(
                item.get("soft_skills") or []))
            + "</div>"
        )
    return "".join(blocks)


def _education(items: list) -> str:
    blocks = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        head = item.get("degree") or item.get("title") or ""
        sub = " · ".join(p for p in [
            item.get("institution"),
            " / ".join(p for p in [item.get("start"), item.get("end")]
                       if p),
            item.get("level"), item.get("status"),
        ] if p)
        blocks.append(
            '<div class="item">'
            f'<div class="item-head"><strong>{esc(head)}</strong></div>'
            + (f'<div class="item-meta">{esc(sub)}</div>' if sub else "")
            + (f'<p class="desc">{esc(item.get("description"))}</p>'
               if item.get("description") else "")
            + "</div>"
        )
    return "".join(blocks)


def _projects(items: list) -> str:
    blocks = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        links = " · ".join(p for p in [
            item.get("url"), item.get("repo")] if p)
        dates = " / ".join(p for p in [item.get("start"), item.get("end")]
                           if p)
        blocks.append(
            '<div class="item">'
            f'<div class="item-head"><strong>{esc(item.get("name"))}'
            f"</strong></div>"
            + (f'<div class="item-meta">{esc(dates)}</div>' if dates else "")
            + (f'<p class="desc">{esc(item.get("description"))}</p>'
               if item.get("description") else "")
            + (f'<p class="desc">{esc(links)}</p>' if links else "")
            + _chips(item.get("technologies"))
            + "</div>"
        )
    return "".join(blocks)


def _certifications(items: list) -> str:
    blocks = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        sub = " · ".join(p for p in [
            item.get("institution"), item.get("issued"),
            ("Vence: " + item["expiry"]) if item.get("expiry") else "",
            ("ID: " + item["credential_id"]) if item.get(
                "credential_id") else "",
        ] if p)
        blocks.append(
            '<div class="item">'
            f'<div class="item-head"><strong>{esc(item.get("name"))}'
            f"</strong></div>"
            + (f'<div class="item-meta">{esc(sub)}</div>' if sub else "")
            + (f'<p class="desc">{esc(item.get("description"))}</p>'
               if item.get("description") else "")
            + "</div>"
        )
    return "".join(blocks)


def _languages(items: list) -> str:
    lines = []
    for lang in items or []:
        if not isinstance(lang, dict):
            continue
        detail = " · ".join(p for p in [
            f"General {lang['level']}" if lang.get("level") else "",
            f"Listening {lang['listening']}" if lang.get("listening") else "",
            f"Reading {lang['reading']}" if lang.get("reading") else "",
            f"Writing {lang['writing']}" if lang.get("writing") else "",
            f"Speaking {lang['speaking']}" if lang.get("speaking") else "",
            lang.get("academy") or "",
        ] if p)
        lines.append(
            f'<p class="lang-line"><strong>{esc(lang.get("label"))}</strong>'
            + (f" — {esc(detail)}" if detail else "") + "</p>")
    return "".join(lines)


def render_cv_html(content: dict, job: dict | None = None) -> str:
    """Construye el HTML final. Lanza ValueError si queda vacio."""
    template = (_templates_dir() / "cv.html").read_text(encoding="utf-8")
    css = (_templates_dir() / "cv.css").read_text(encoding="utf-8")

    target = ""
    if job and (job.get("title") or job.get("company")):
        target = (
            '<div class="target-block">CV adaptado para: '
            f"<strong>{esc(job.get('title'))}</strong>"
            + (f" · {esc(job.get('company'))}" if job.get("company")
               else "")
            + "</div>"
        )

    summary = ""
    if str(content.get("summary") or "").strip():
        summary = (
            "<section><h2>Resumen profesional</h2>"
            f'<p class="summary">{esc(content.get("summary"))}</p></section>'
        )

    title_line = " · ".join(p for p in [
        content.get("target_role"), content.get("title")] if p)
    if not title_line:
        title_line = str(content.get("company") or "")

    titles = {
        "CSS": css,
        "FULL_NAME": esc(content.get("full_name")),
        "TITLE_LINE": esc(title_line),
        "CONTACT_LINE": _contact_line(content),
        "TARGET_BLOCK": target,
        "SUMMARY_BLOCK": summary,
        "SKILLS_BLOCK": _section(
            "Habilidades", _chips(content.get("skills"))),
        "EXPERIENCE_BLOCK": _section(
            "Experiencia", _experience(content.get("experiences"))),
        "PROJECTS_BLOCK": _section(
            "Proyectos", _projects(content.get("projects"))),
        "EDUCATION_BLOCK": _section(
            "Educación", _education(content.get("education"))),
        "CERTIFICATIONS_BLOCK": _section(
            "Certificaciones",
            _certifications(content.get("certifications"))),
        "LANGUAGES_BLOCK": _section(
            "Idiomas", _languages(content.get("languages"))),
    }
    html_text = template
    for key, value in titles.items():
        html_text = html_text.replace("{{" + key + "}}", value)
    if not content.get("full_name") and "<section>" not in html_text:
        raise ValueError("Contenido insuficiente para generar el HTML.")
    return html_text
