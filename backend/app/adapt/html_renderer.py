"""Render HTML del CV (FASE 6 - Rediseño según plantilla ejemplo).

Plantilla reutilizable (templates/cv.html + cv.css) + datos
escapados. La plantilla no ejecuta JavaScript (Chromium con JS apagado).
Estructura basada en el CV de ejemplo: nombre, título profesional, contacto,
resumen, competencias técnicas (categorizadas), habilidades blandas,
experiencia con bullets, proyectos, educación, otros estudios, otros conocimientos, idiomas.
"""
from __future__ import annotations

import html
from pathlib import Path


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _contact_line(content: dict) -> str:
    parts = [
        content.get("location"),
        content.get("phone"),
        content.get("email"),
        content.get("linkedin"),
        content.get("github"),
        content.get("portfolio"),
    ]
    return " | ".join(esc(p) for p in parts if str(p).strip())


def _section(title: str, inner: str) -> str:
    if not inner.strip():
        return ""
    return f"<section><h2>{esc(title)}</h2>{inner}</section>"


def _chips_html(items: list | None) -> str:
    """Genera HTML para chips de tecnologías/habilidades."""
    if not items:
        return ""
    valid_items = [str(t).strip() for t in items if str(t).strip()]
    if not valid_items:
        return ""
    chip_template = '<span class="chip">{}</span>'
    return '<div class="chips">' + "".join(chip_template.format(esc(t)) for t in valid_items) + "</div>"


def _technical_skills_block(content: dict) -> str:
    """Genera bloque de competencias técnicas categorizadas."""
    skills_groups = content.get("skills_groups") or {}
    # Mapeo de claves a títulos legibles
    category_map = {
        "analysis": "Análisis de Datos",
        "languages": "Lenguajes y Análisis",
        "bi": "BI y Visualización",
        "databases": "Bases de Datos",
        "automation": "Automatización y APIs",
        "backend": "Desarrollo Backend (proyectos personales)",
        "ml": "Machine Learning / Computer Vision (proyectos personales)",
        "tools": "Herramientas",
    }

    blocks = []
    for key, title in category_map.items():
        items = skills_groups.get(key) or []
        if items:
            items_str = ", ".join(esc(i) for i in items if str(i).strip())
            if items_str:
                blocks.append(
                    f'<div class="skills-category">'
                    f'<div class="skills-category-title">{esc(title)}</div>'
                    f'<p class="skills-list">{items_str}</p>'
                    f"</div>"
                )

    # También incluir skills_technical plano si no hay grupos
    if not blocks:
        flat_skills = content.get("skills_technical") or []
        if flat_skills:
            items_str = ", ".join(esc(s) for s in flat_skills if str(s).strip())
            if items_str:
                blocks.append(
                    f'<div class="skills-category">'
                    f'<div class="skills-category-title">Competencias Técnicas</div>'
                    f'<p class="skills-list">{items_str}</p>'
                    f"</div>"
                )

    if not blocks:
        return ""

    return _section("Competencias Técnicas", "".join(blocks))


def _soft_skills_block(content: dict) -> str:
    """Genera bloque de habilidades blandas con descripción."""
    soft_skills = content.get("skills_soft") or []
    if not soft_skills:
        return ""

    # Mapeo de habilidades a descripciones (basado en el CV ejemplo)
    descriptions = {
        "Pensamiento analítico": "análisis e interpretación de información para apoyar la toma de decisiones.",
        "Comunicación y trabajo en equipo": "capacidad para comunicar información y colaborar con diferentes áreas y equipos.",
        "Orientación a resultados": "enfoque en el cumplimiento de objetivos e indicadores.",
        "Atención al detalle": "validación, revisión y organización de información para mantener la calidad de los datos.",
        "Pensamiento crítico": "evaluación objetiva de información para resolver problemas complejos.",
        "Adaptabilidad": "capacidad de ajustarse a nuevos entornos y tecnologías rápidamente.",
        "Organización": "gestión eficiente del tiempo y recursos en proyectos múltiples.",
        "Resolución de problemas": "identificación y solución de inconvenientes técnicos y de negocio.",
        "Aprendizaje autónomo": "actualización continua de conocimientos técnicos por iniciativa propia.",
        "Trabajo en equipo": "colaboración efectiva en equipos multidisciplinarios.",
    }

    items = []
    for skill in soft_skills:
        skill_str = str(skill).strip()
        if not skill_str:
            continue
        desc = descriptions.get(skill_str, "")
        if desc:
            items.append(
                f'<div class="soft-skill-item">'
                f'<span class="soft-skill-label">{esc(skill_str)}:</span> '
                f'<span class="soft-skill-desc">{esc(desc)}</span>'
                f"</div>"
            )
        else:
            items.append(
                f'<div class="soft-skill-item">'
                f'<span class="soft-skill-label">{esc(skill_str)}</span>'
                f"</div>"
            )

    if not items:
        return ""

    return _section(
        "Habilidades Blandas",
        f'<div class="soft-skills-list">{"".join(items)}</div>'
    )


def _experience_block(content: dict) -> str:
    """Genera bloque de experiencia profesional con bullets."""
    experiences = content.get("experiences") or []
    blocks = []

    for exp in experiences:
        if not isinstance(exp, dict):
            continue

        company = exp.get("company") or ""
        role = exp.get("title") or exp.get("role") or ""
        city = exp.get("city") or exp.get("location") or ""
        modality = exp.get("modality") or ""
        start = exp.get("start") or exp.get("start_date") or ""
        end = exp.get("end") or exp.get("end_date") or ""
        is_current = exp.get("is_current") or False
        description = exp.get("description") or ""
        bullets = exp.get("bullets") or exp.get("achievements") or []
        tech_skills = exp.get("technical_skills") or []
        soft_skills = exp.get("soft_skills") or []

        # Header: role + company
        head_parts = []
        if role:
            head_parts.append(f'<span class="item-role">{esc(role)}</span>')
        if company:
            head_parts.append(f'<span class="item-company">{esc(company)}</span>')

        # Meta: dates + location + modality
        meta_parts = []
        if start or end or is_current:
            if is_current:
                date_str = f"{esc(start)} – Actualidad"
            else:
                date_str = f"{esc(start)} – {esc(end)}" if start and end else (esc(start) or esc(end))
            meta_parts.append(date_str)
        if city:
            meta_parts.append(esc(city))
        if modality:
            meta_parts.append(esc(modality))

        # Bullets
        bullet_items = ""
        if bullets:
            bullet_items = '<ul class="item-bullets">' + "".join(
                f"<li>{esc(b)}</li>" for b in bullets if str(b).strip()
            ) + "</ul>"

        # Skills chips
        all_skills = list(tech_skills) + list(soft_skills)
        chips = ""
        if all_skills:
            chips = '<div class="chips">' + "".join(
                f'<span class="chip">{esc(s)}</span>' for s in all_skills if str(s).strip()
            ) + "</div>"

        blocks.append(
            '<div class="item">'
            f'<div class="item-head">{"".join(head_parts)}</div>'
            + (f'<div class="item-meta">{" · ".join(meta_parts)}</div>' if meta_parts else "")
            + (f'<p class="item-desc">{esc(description)}</p>' if description else "")
            + bullet_items
            + chips
            + "</div>"
        )

    if not blocks:
        return ""

    return _section("Experiencia Profesional", "".join(blocks))


def _projects_block(content: dict) -> str:
    """Genera bloque de proyectos destacados."""
    projects = content.get("projects") or []
    blocks = []

    for proj in projects:
        if not isinstance(proj, dict):
            continue

        name = proj.get("name") or proj.get("title") or ""
        description = proj.get("description") or ""
        technologies = proj.get("technologies") or proj.get("technical_skills") or []
        url = proj.get("url") or ""
        repo = proj.get("repo") or ""
        start = proj.get("start") or proj.get("start_date") or ""
        end = proj.get("end") or proj.get("end_date") or ""

        meta_parts = []
        if start or end:
            date_str = f"{esc(start)} – {esc(end)}" if start and end else (esc(start) or esc(end))
            meta_parts.append(date_str)

        links = " · ".join(esc(p) for p in [url, repo] if str(p).strip())

        blocks.append(
            '<div class="item">'
            f'<div class="item-head"><span class="item-role">{esc(name)}</span></div>'
            + (f'<div class="item-meta">{" · ".join(meta_parts)}</div>' if meta_parts else "")
            + (f'<p class="item-desc">{esc(description)}</p>' if description else "")
            + (f'<p class="item-desc">{esc(links)}</p>' if links else "")
            + _chips_html(technologies)
            + "</div>"
        )

    if not blocks:
        return ""

    return _section("Proyectos Destacados", "".join(blocks))


def _education_block(content: dict) -> str:
    """Genera bloque de educación."""
    education = content.get("education") or []
    blocks = []

    for edu in education:
        if not isinstance(edu, dict):
            continue

        degree = edu.get("degree") or edu.get("title") or ""
        institution = edu.get("institution") or ""
        level = edu.get("level") or ""
        status = edu.get("status") or ""
        start = edu.get("start") or edu.get("start_date") or ""
        end = edu.get("end") or edu.get("end_date") or ""
        description = edu.get("description") or ""

        meta_parts = []
        if institution:
            meta_parts.append(esc(institution))
        if level:
            meta_parts.append(esc(level))
        if status:
            meta_parts.append(esc(status))
        if start or end:
            date_str = f"{esc(start)} – {esc(end)}" if start and end else (esc(start) or esc(end))
            meta_parts.append(date_str)

        blocks.append(
            '<div class="education-item">'
            f'<div class="education-degree">{esc(degree)}</div>'
            + (f'<div class="education-institution">{" · ".join(meta_parts)}</div>' if meta_parts else "")
            + (f'<div class="education-dates">{esc(description)}</div>' if description else "")
            + "</div>"
        )

    if not blocks:
        return ""

    return _section("Educación", "".join(blocks))


def _other_studies_block(content: dict) -> str:
    """Genera bloque de otros estudios/cursos complementarios."""
    # Buscar en education items que parezcan cursos/otros estudios
    # O en un campo específico si existe
    other_studies = content.get("other_studies") or []
    if not other_studies:
        # Intentar extraer de education items con level tipo "course"
        education = content.get("education") or []
        other_studies = [
            e for e in education
            if isinstance(e, dict) and str(e.get("level", "")).lower() in ("course", "certification", "other")
        ]

    if not other_studies:
        return ""

    blocks = []
    for study in other_studies:
        if not isinstance(study, dict):
            continue

        title = study.get("title") or study.get("degree") or ""
        institution = study.get("institution") or study.get("academy") or ""
        start = study.get("start") or study.get("start_date") or ""
        end = study.get("end") or study.get("end_date") or ""

        date_str = ""
        if start or end:
            date_str = f"{esc(start)} – {esc(end)}" if start and end else (esc(start) or esc(end))

        blocks.append(
            '<div class="study-item">'
            f'<span class="study-title">{esc(title)}</span>'
            + (f' <span class="study-institution">{esc(institution)}</span>' if institution else "")
            + (f' <span class="study-dates">({date_str})</span>' if date_str else "")
            + "</div>"
        )

    if not blocks:
        return ""

    return _section("Otros Estudios", "".join(blocks))


def _other_knowledge_block(content: dict) -> str:
    """Genera bloque de otros conocimientos/metodologías."""
    knowledge = content.get("other_knowledge") or []
    if not knowledge:
        # Intentar extraer de skills_groups
        skills_groups = content.get("skills_groups") or {}
        methodologies = skills_groups.get("methodologies") or skills_groups.get("concepts") or []
        if methodologies:
            knowledge = methodologies

    if not knowledge:
        return ""

    text = ", ".join(esc(k) for k in knowledge if str(k).strip())
    if not text:
        return ""

    return _section(
        "Otros Conocimientos",
        f'<p class="knowledge-text">{text}</p>'
    )


def _languages_block(content: dict) -> str:
    """Genera bloque de idiomas."""
    languages = content.get("languages") or []
    lines = []

    for lang in languages:
        if not isinstance(lang, dict):
            continue

        label = lang.get("label") or lang.get("language_label") or lang.get("language") or ""
        level = lang.get("level") or ""
        listening = lang.get("listening") or ""
        reading = lang.get("reading") or ""
        writing = lang.get("writing") or ""
        speaking = lang.get("speaking") or ""
        academy = lang.get("academy") or ""

        detail_parts = []
        if level:
            detail_parts.append(f"General {esc(level)}")
        if listening:
            detail_parts.append(f"Listening {esc(listening)}")
        if reading:
            detail_parts.append(f"Reading {esc(reading)}")
        if writing:
            detail_parts.append(f"Writing {esc(writing)}")
        if speaking:
            detail_parts.append(f"Speaking {esc(speaking)}")
        if academy:
            detail_parts.append(esc(academy))

        detail = " · ".join(detail_parts)
        if detail:
            lines.append(
                f'<p class="lang-line"><strong>{esc(label)}</strong> — {esc(detail)}</p>'
            )
        else:
            lines.append(
                f'<p class="lang-line"><strong>{esc(label)}</strong></p>'
            )

    if not lines:
        return ""

    return _section("Idiomas", "".join(lines))


def render_cv_html(content: dict, job: dict | None = None) -> str:
    """Construye el HTML final. Lanza ValueError si queda vacio."""
    template = (_templates_dir() / "cv.html").read_text(encoding="utf-8")
    css = (_templates_dir() / "cv.css").read_text(encoding="utf-8")

    # Título profesional
    professional_title = content.get("target_role") or content.get("title") or content.get("professional_title") or ""
    if not professional_title and content.get("target_roles"):
        professional_title = content["target_roles"][0]

    # Target block
    target = ""
    if job and (job.get("title") or job.get("company")):
        target = (
            '<div class="target-block">CV adaptado para: '
            f"<strong>{esc(job.get('title'))}</strong>"
            + (f" · {esc(job.get('company'))}" if job.get("company") else "")
            + "</div>"
        )

    # Summary
    summary = ""
    if str(content.get("summary") or "").strip():
        summary = _section(
            "Perfil Profesional",
            f'<p class="summary">{esc(content.get("summary"))}</p>'
        )

    titles = {
        "CSS": css,
        "FULL_NAME": esc(content.get("full_name")),
        "PROFESSIONAL_TITLE": esc(professional_title),
        "CONTACT_LINE": _contact_line(content),
        "TARGET_BLOCK": target,
        "SUMMARY_BLOCK": summary,
        "TECHNICAL_SKILLS_BLOCK": _technical_skills_block(content),
        "SOFT_SKILLS_BLOCK": _soft_skills_block(content),
        "EXPERIENCE_BLOCK": _experience_block(content),
        "PROJECTS_BLOCK": _projects_block(content),
        "EDUCATION_BLOCK": _education_block(content),
        "OTHER_STUDIES_BLOCK": _other_studies_block(content),
        "OTHER_KNOWLEDGE_BLOCK": _other_knowledge_block(content),
        "LANGUAGES_BLOCK": _languages_block(content),
    }

    html_text = template
    for key, value in titles.items():
        html_text = html_text.replace("{{" + key + "}}", value)

    if not content.get("full_name") and "<section>" not in html_text:
        raise ValueError("Contenido insuficiente para generar el HTML.")

    return html_text