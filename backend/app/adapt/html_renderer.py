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


MESES = {"01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
         "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
         "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic"}


def _fmt_month(value: str | None) -> str:
    """'03/2025' o '2025-03-01' -> 'Mar 2025'. Ilegible se devuelve tal cual."""
    import re as _re

    text = str(value or "").strip()
    match = _re.match(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$", text)
    if match:
        return f"{MESES.get(match.group(2).zfill(2), match.group(2))} {match.group(1)}"
    match = _re.match(r"^(\d{1,2})/(\d{4})$", text)
    if match:
        return f"{MESES.get(match.group(1).zfill(2), match.group(1))} {match.group(2)}"
    return text


def _fmt_day(value: str | None) -> str:
    """'2026-07-15' -> '15 Jul 2026'."""
    import re as _re

    text = str(value or "").strip()
    match = _re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if match:
        return (f"{int(match.group(3))} "
                f"{MESES.get(match.group(2).zfill(2), match.group(2))} "
                f"{match.group(1)}")
    return _fmt_month(text) if text else ""


def _display_url(url: str | None) -> str:
    """Quita esquema para mostrar (linkedin.com/...) como en el ejemplo."""
    import re as _re

    text = str(url or "").strip()
    text = _re.sub(r"^https?://", "", text).rstrip("/")
    return text


def _split_sentences(text: str) -> list[str]:
    """Divide en oraciones sin inventar contenido (corta en '. ' + mayuscula)."""
    import re as _re

    parts = [_re.sub(r"\s+", " ", p).strip()
             for p in _re.split(r"\.\s+(?=[A-ZÁÉÍÓÚÑ0-9])", str(text or ""))]
    sentences = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i < len(parts) - 1 and not part.endswith("."):
            part += "."
        sentences.append(part)
    return sentences


def _contact_lines(content: dict) -> tuple[str, str]:
    """Dos lineas como el ejemplo: ubicacion|tel|email y enlaces."""
    line1 = [content.get("location"), content.get("phone"),
             content.get("email")]
    line2 = [_display_url(content.get("linkedin")),
             _display_url(content.get("github")),
             _display_url(content.get("portfolio"))]
    first = " | ".join(esc(p) for p in line1 if str(p).strip())
    second = " | ".join(esc(p) for p in line2 if str(p).strip())
    return first, second


def _section(title: str, inner: str) -> str:
    if not inner.strip():
        return ""
    return f"<section><h2>{esc(title)}</h2>{inner}</section>"


def _technical_skills_block(content: dict) -> str:
    """Genera bloque de competencias técnicas categorizadas."""
    skills_groups = content.get("skills_groups") or {}
    # Mapeo de claves a títulos legibles (acepta las claves del fixture
    # demo y variantes de otros perfiles).
    category_map = {
        "analysis": "Análisis de Datos",
        "data_analysis": "Análisis de Datos",
        "languages": "Lenguajes y Análisis",
        "programming": "Lenguajes de Programación",
        "bi": "BI y Visualización",
        "databases": "Bases de Datos",
        "automation": "Automatización y APIs",
        "backend": "Desarrollo Backend",
        "ml": "Machine Learning / Computer Vision",
        "tools": "Herramientas",
        "business": "Negocios e Inteligencia de Negocios",
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

    return _section("Habilidades Técnicas", "".join(blocks))


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
    """Experiencia estilo ejemplo: cargo, fechas, empresa, Responsabilidad
    General (primera oracion) + bullets con el resto. Sin chips: las
    skills van en su seccion; aqui una linea discreta las conserva."""
    experiences = content.get("experiences") or []
    blocks = []

    for exp in experiences:
        if not isinstance(exp, dict):
            continue

        role = exp.get("title") or exp.get("role") or ""
        company = exp.get("company") or ""
        city = exp.get("city") or exp.get("location") or ""
        start = _fmt_month(exp.get("start") or exp.get("start_date") or "")
        end_raw = exp.get("end") or exp.get("end_date") or ""
        if exp.get("is_current"):
            dates = f"{start} – Actualidad" if start else "Actualidad"
        elif start and _fmt_month(end_raw):
            dates = f"{start} – {_fmt_month(end_raw)}"
        else:
            dates = start or _fmt_month(end_raw)

        sentences = _split_sentences(exp.get("description") or "")
        general = (f'<p class="item-p"><strong>Responsabilidad General:</strong> '
                   f"{esc(sentences[0])}</p>") if sentences else ""
        # Bullets del autor si existen; si no, se derivan del resto de
        # oraciones sin inventar contenido.
        explicit = [str(b).strip() for b in
                    (exp.get("bullets") or exp.get("achievements") or [])
                    if str(b).strip()]
        rest = sentences[1:] if len(sentences) > 1 else []
        items = explicit or rest
        bullets = ""
        if items:
            bullets = '<ul class="item-bullets">' + "".join(
                f"<li>{esc(b)}</li>" for b in items) + "</ul>"

        entry_skills = list(exp.get("technical_skills") or []) + list(
            exp.get("soft_skills") or [])
        skills_line = ""
        if entry_skills:
            skills_line = (
                '<p class="skills-line"><strong>Habilidades:</strong> '
                + esc(", ".join(str(s) for s in entry_skills)) + "</p>")

        org = f"{esc(company)} – {esc(city)}" if company and city else (
            esc(company or city))
        blocks.append(
            '<div class="item">'
            + (f'<p class="item-title">{esc(role)}</p>' if role else "")
            + (f'<p class="item-dates">{esc(dates)}</p>' if dates else "")
            + (f'<p class="item-org">{org}</p>' if org else "")
            + general + bullets + skills_line
            + "</div>"
        )

    if not blocks:
        return ""

    return _section("Experiencia Profesional / Professional Experience",
                    "".join(blocks))


def _projects_block(content: dict) -> str:
    """Proyectos estilo ejemplo: nombre, parrafos y linea de tecnologias."""
    projects = content.get("projects") or []
    blocks = []

    for proj in projects:
        if not isinstance(proj, dict):
            continue

        name = proj.get("name") or proj.get("title") or ""
        start = _fmt_month(proj.get("start") or proj.get("start_date") or "")
        end = _fmt_month(proj.get("end") or proj.get("end_date") or "")
        dates = f"{start} – {end}" if start and end else (start or end)
        links = " · ".join(_display_url(p) for p in
                           [proj.get("url"), proj.get("repo")] if str(p).strip())
        techs = list(proj.get("technologies") or proj.get("technical_skills") or [])

        blocks.append(
            '<div class="item">'
            + (f'<p class="item-title">{esc(name)}</p>' if name else "")
            + (f'<p class="item-dates">{esc(dates)}</p>' if dates else "")
            + (f'<p class="item-p">{esc(proj.get("description"))}</p>'
               if proj.get("description") else "")
            + (f'<p class="item-p">{esc(links)}</p>' if links else "")
            + (f'<p class="skills-line"><strong>Tecnologías:</strong> '
               f'{esc(", ".join(str(t) for t in techs))}</p>' if techs else "")
            + "</div>"
        )

    if not blocks:
        return ""

    return _section("Proyectos Destacados", "".join(blocks))


def _education_block(content: dict) -> str:
    """Educacion estilo ejemplo: titulo, fechas, institucion, parrafo."""
    education = content.get("education") or []
    blocks = []

    for edu in education:
        if not isinstance(edu, dict):
            continue

        degree = edu.get("degree") or edu.get("title") or ""
        institution = edu.get("institution") or ""
        start = _fmt_month(edu.get("start") or edu.get("start_date") or "")
        end = _fmt_month(edu.get("end") or edu.get("end_date") or "")
        dates = f"{start} – {end}" if start and end else (start or end)

        blocks.append(
            '<div class="item">'
            + (f'<p class="item-title">{esc(degree)}</p>' if degree else "")
            + (f'<p class="item-dates">{esc(dates)}</p>' if dates else "")
            + (f'<p class="item-org">{esc(institution)}</p>'
               if institution else "")
            + (f'<p class="item-p">{esc(edu.get("description"))}</p>'
               if edu.get("description") else "")
            + "</div>"
        )

    if not blocks:
        return ""

    return _section("Educación / Education", "".join(blocks))


def _other_studies_block(content: dict) -> str:
    """Otros Estudios estilo ejemplo: certificaciones + cursos sueltos.
    Las certificaciones van aqui porque el ejemplo no trae seccion
    separada para ellas."""
    other_studies = content.get("other_studies") or []
    if not other_studies:
        education = content.get("education") or []
        other_studies = [
            e for e in education
            if isinstance(e, dict) and str(e.get("level", "")).lower() in ("course", "certification", "other")
        ]

    blocks = []
    for study in other_studies:
        if not isinstance(study, dict):
            continue

        title = study.get("title") or study.get("degree") or ""
        institution = study.get("institution") or study.get("academy") or ""
        start = _fmt_month(study.get("start") or study.get("start_date") or "")
        end = _fmt_month(study.get("end") or study.get("end_date") or "")
        dates = f"{start} – {end}" if start and end else (start or end)

        blocks.append(
            '<div class="study-item">'
            + (f'<p class="item-title">{esc(title)}</p>' if title else "")
            + (f'<p class="item-dates">{esc(dates)}</p>' if dates else "")
            + (f'<p class="item-org">{esc(institution)}</p>'
               if institution else "")
            + (f'<p class="item-p">{esc(study.get("description"))}</p>'
               if study.get("description") else "")
            + "</div>"
        )

    for cert in content.get("certifications") or []:
        if not isinstance(cert, dict):
            continue
        issued = _fmt_day(cert.get("issued") or cert.get("issued_date") or "")
        expiry = _fmt_day(cert.get("expiry") or cert.get("expiry_date") or "")
        dates = f"{issued} – {expiry}" if issued and expiry else (
            issued or expiry)
        cred = cert.get("credential_id") or ""
        blocks.append(
            '<div class="study-item">'
            + (f'<p class="item-title">{esc(cert.get("name"))}</p>'
               if cert.get("name") else "")
            + (f'<p class="item-dates">{esc(dates)}</p>' if dates else "")
            + (f'<p class="item-org">{esc(cert.get("institution"))}</p>'
               if cert.get("institution") else "")
            + (f'<p class="item-p">{esc(cert.get("description"))}</p>'
               if cert.get("description") else "")
            + (f'<p class="item-p">ID: {esc(cred)}</p>' if cred else "")
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

    # Linea de titulo estilo ejemplo: rol adaptado | titulo de la persona.
    adapted = str(content.get("target_role") or "").strip()
    own = str(content.get("title") or "").strip()
    if adapted and own and adapted.lower() != own.lower():
        professional_title = f"{adapted} | {own}"
    else:
        professional_title = adapted or own

    line1, line2 = _contact_lines(content)

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
        "TITLE_LINE": esc(professional_title),
        "CONTACT_LINE_1": line1,
        "CONTACT_LINE_2": line2,
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