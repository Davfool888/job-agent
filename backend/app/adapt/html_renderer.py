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


MESES_FULL = {"01": "Enero", "02": "Febrero", "03": "Marzo",
              "04": "Abril", "05": "Mayo", "06": "Junio",
              "07": "Julio", "08": "Agosto", "09": "Septiembre",
              "10": "Octubre", "11": "Noviembre", "12": "Diciembre"}


def _parse_ymd(value: str | None) -> tuple | None:
    """(año, mes, dia|None) desde ISO, MM/YYYY, 'Mar 2025' o YYYY."""
    import re as _re

    text = str(value or "").strip()
    match = _re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$", text)
    if match:
        return match.group(1), match.group(2).zfill(2), match.group(3)
    match = _re.match(r"^(\d{1,2})/(\d{4})$", text)
    if match:
        return match.group(2), match.group(1).zfill(2), None
    match = _re.match(r"^([A-Za-zÁÉÍÓÚÑáéíóúñ]+)\s+(\d{4})$", text)
    if match:
        inv = {v.lower(): k for k, v in list(MESES.items())
               + [(v.lower(), k) for k, v in MESES_FULL.items()]}
        month = inv.get(match.group(1).lower())
        if month:
            return match.group(2), month, None
    match = _re.match(r"^(\d{4})$", text)
    if match:
        return match.group(1), None, None
    return None


def _fmt_month(value: str | None, fmt: str = "MMM YYYY") -> str:
    """Formatea mes segun date_format ('Mar 2025' por defecto)."""
    parsed = _parse_ymd(value)
    if not parsed:
        return str(value or "").strip()
    year, month, _day = parsed
    if month is None:
        return year
    if fmt == "MM/YYYY":
        return f"{month}/{year}"
    if fmt == "MM/YY":
        return f"{month}/{year[2:]}"
    if fmt == "MMMM YYYY":
        return f"{MESES_FULL.get(month, month)} {year}"
    if fmt == "YYYY-MM":
        return f"{year}-{month}"
    return f"{MESES.get(month, month)} {year}"


def _fmt_day(value: str | None, fmt: str = "MMM YYYY") -> str:
    """Formatea fecha con dia segun date_format."""
    parsed = _parse_ymd(value)
    if not parsed:
        return str(value or "").strip()
    year, month, day = parsed
    if month is None:
        return year
    if fmt == "MM/YYYY":
        return f"{month}/{year}" if not day else (
            f"{day.zfill(2)}/{month}/{year}")
    if fmt == "MM/YY":
        short = year[2:]
        return f"{month}/{short}" if not day else (
            f"{day.zfill(2)}/{month}/{short}")
    if fmt == "MMMM YYYY":
        base = f"{MESES_FULL.get(month, month)} {year}"
        return f"{int(day)} de {base}" if day else base
    if fmt == "YYYY-MM":
        return f"{year}-{month}" if not day else (
            f"{year}-{month}-{day.zfill(2)}")
    if day:
        return f"{int(day)} {MESES.get(month, month)} {year}"
    return f"{MESES.get(month, month)} {year}"


def _display_url(url: str | None) -> str:
    """Quita esquema para mostrar (linkedin.com/...) como en el ejemplo."""
    import re as _re

    text = str(url or "").strip()
    text = _re.sub(r"^https?://", "", text).rstrip("/")
    return text


def _strip_general_label(text: str) -> str:
    """Quita 'Responsabilidad General:' inicial si ya viene en los datos.

    El renderer antepone esa etiqueta; si la descripcion la trae (perfil
    importado de un CV ya generado o reescritura LLM), saldria duplicada.
    Solo con dos puntos (sin ':' podria ser inicio legitimo de frase).
    """
    import re as _re

    return _re.sub(r"^(responsabilidad general\s*:\s*)+", "",
                   str(text or "").strip(), flags=_re.IGNORECASE)


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


def _fit_profile_length(text: str, length: str) -> str:
    """Recorta el perfil a short (~450) o medium (~900) por oraciones.

    Subconjunto honesto: nunca reescribe, solo corta en frontera de
    oracion. 'full' (defecto) no recorta.
    """
    budgets = {"short": 450, "medium": 900}
    budget = budgets.get(str(length or "").lower())
    cleaned = str(text or "").strip()
    if not budget or len(cleaned) <= budget:
        return cleaned
    kept: list[str] = []
    total = 0
    for sentence in _split_sentences(cleaned):
        if total + len(sentence) > budget and kept:
            break
        kept.append(sentence)
        total += len(sentence) + 1
    out = " ".join(kept).strip()
    return out + (" …" if len(out) < len(cleaned) else "")


def _contact_lines(content: dict, show_links: bool = True) -> tuple[str, str]:
    """Dos lineas como el ejemplo: ubicacion|tel|email y enlaces.

    Lo importante que falte no se inventa: se marca en el mismo
    pedazo con '(falta información de ...)'. Con show_links=False
    se omite la linea de enlaces.
    """
    missing = set(content.get("missing") or [])
    line1 = [content.get("location"), content.get("phone"),
             content.get("email")]
    if "phone" in missing:
        line1.append(_missing_text("phone"))
    if "email" in missing:
        line1.append(_missing_text("email"))
    line2 = ([_display_url(content.get("linkedin")),
              _display_url(content.get("github")),
              _display_url(content.get("portfolio"))] if show_links else [])
    first = " | ".join(esc(p) for p in line1 if str(p).strip())
    second = " | ".join(esc(p) for p in line2 if str(p).strip())
    return first, second


MISSING_LABELS = {
    "title": "título profesional",
    "email": "correo electrónico",
    "phone": "teléfono",
    "summary": "resumen profesional",
    "skills": "habilidades",
    "experiences": "experiencia laboral",
    "education": "educación",
}


def _missing_text(code: str) -> str:
    return f"(falta información de {MISSING_LABELS.get(code, code)})"


def _missing_block(content: dict, code: str) -> str:
    """Parrafo marcador para secciones sin datos del perfil."""
    if code in (content.get("missing") or []):
        return (f'<p class="missing-info">'
                f"{esc(_missing_text(code))}</p>")
    return ""


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
        return _section("Competencias Técnicas",
                        _missing_block(content, "skills"))

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


def _experience_block(content: dict, fmt: str = "MMM YYYY",
                      max_bullets: int = 0) -> str:
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
        start = _fmt_month(exp.get("start") or exp.get("start_date") or "", fmt)
        end_raw = exp.get("end") or exp.get("end_date") or ""
        if exp.get("is_current"):
            dates = f"{start} – Actualidad" if start else "Actualidad"
        elif start and _fmt_month(end_raw, fmt):
            dates = f"{start} – {_fmt_month(end_raw, fmt)}"
        else:
            dates = start or _fmt_month(end_raw, fmt)

        sentences = _split_sentences(
            _strip_general_label(exp.get("description") or ""))
        general = (f'<p class="item-p"><strong>Responsabilidad General:</strong> '
                   f"{esc(sentences[0])}</p>") if sentences else ""
        # Bullets del autor si existen; si no, se derivan del resto de
        # oraciones sin inventar contenido.
        explicit = [str(b).strip() for b in
                    (exp.get("bullets") or exp.get("achievements") or [])
                    if str(b).strip()]
        rest = sentences[1:] if len(sentences) > 1 else []
        items = explicit or rest
        if max_bullets > 0:
            items = items[:max_bullets]
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
        return _section("Experiencia Profesional / Professional Experience",
                        _missing_block(content, "experiences"))

    return _section("Experiencia Profesional / Professional Experience",
                    "".join(blocks))


def _projects_block(content: dict, fmt: str = "MMM YYYY") -> str:
    """Proyectos estilo ejemplo: nombre, parrafos y linea de tecnologias."""
    projects = content.get("projects") or []
    blocks = []

    for proj in projects:
        if not isinstance(proj, dict):
            continue

        name = proj.get("name") or proj.get("title") or ""
        start = _fmt_month(proj.get("start") or proj.get("start_date") or "", fmt)
        end = _fmt_month(proj.get("end") or proj.get("end_date") or "", fmt)
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


def _education_block(content: dict, fmt: str = "MMM YYYY") -> str:
    """Educacion estilo ejemplo: titulo, fechas, institucion, parrafo."""
    education = content.get("education") or []
    blocks = []

    for edu in education:
        if not isinstance(edu, dict):
            continue

        degree = edu.get("degree") or edu.get("title") or ""
        institution = edu.get("institution") or ""
        start = _fmt_month(edu.get("start") or edu.get("start_date") or "", fmt)
        end = _fmt_month(edu.get("end") or edu.get("end_date") or "", fmt)
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
        return _section("Educación / Education",
                        _missing_block(content, "education"))

    return _section("Educación / Education", "".join(blocks))


def _other_studies_block(content: dict, fmt: str = "MMM YYYY") -> str:
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
        start = _fmt_month(study.get("start") or study.get("start_date") or "", fmt)
        end = _fmt_month(study.get("end") or study.get("end_date") or "", fmt)
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
        issued = _fmt_day(cert.get("issued") or cert.get("issued_date") or "", fmt)
        expiry = _fmt_day(cert.get("expiry") or cert.get("expiry_date") or "", fmt)
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


def _apply_pdf_config_to_css(css: str, pdf_config: dict) -> str:
    """Aplica la configuración de PDF al CSS.

    Los fallbacks salen de la unica fuente (adapt/defaults.py); el
    servicio normalmente entrega config ya coercionada.
    """
    import re

    from app.adapt.defaults import DEFAULT_PDF_CONFIG as _DEFAULTS

    # Fuente
    font_family = pdf_config.get("font_family", _DEFAULTS["font_family"])
    font_map = {
        "georgia": '"Georgia", "Times New Roman", serif',
        "times": '"Times New Roman", Georgia, serif',
        "arial": '"Arial", "Helvetica Neue", Helvetica, sans-serif',
    }
    css = re.sub(
        r'font-family:\s*[^;]+;',
        f'font-family: {font_map.get(font_family, font_map["georgia"])};',
        css
    )
    
    # Tamaño de fuente base
    font_size = pdf_config.get("font_size_pt", _DEFAULTS["font_size_pt"])
    css = re.sub(
        r'font-size:\s*[\d.]+pt;',
        f'font-size: {font_size}pt;',
        css
    )
    
    # Color de TEXTO siempre negro (sin picker en la UI). Solo
    # propiedades `color:`: el lookbehind excluye `background-color`
    # y bordes. Un regex indiscriminado pintaba `background: #fff`
    # de negro y el PDF salia un rectangulo negro (bug historico).
    css = re.sub(r'(?<![a-zA-Z-])color:\s*#[0-9a-fA-F]{3,6}',
                 'color: #000000', css)
    
    # Márgenes (APA 25mm por defecto centralizado)
    margin_top = pdf_config.get("margin_top_mm", _DEFAULTS["margin_top_mm"])
    margin_bottom = pdf_config.get(
        "margin_bottom_mm", _DEFAULTS["margin_bottom_mm"])
    margin_left = pdf_config.get("margin_left_mm", _DEFAULTS["margin_left_mm"])
    margin_right = pdf_config.get(
        "margin_right_mm", _DEFAULTS["margin_right_mm"])
    css = re.sub(
        r'margin:\s*[\d.]+mm\s+[\d.]+mm\s+[\d.]+mm\s+[\d.]+mm;',
        f'margin: {margin_top}mm {margin_right}mm {margin_bottom}mm {margin_left}mm;',
        css
    )
    
    # Espaciado entre secciones
    spacing = pdf_config.get(
        "section_spacing_pt", _DEFAULTS["section_spacing_pt"])
    css = re.sub(
        r'section\s*\{\s*margin-bottom:\s*[\d.]+pt;',
        f'section {{ margin-bottom: {spacing}pt;',
        css
    )
    
    # Modo compacto
    if pdf_config.get("compact_mode"):
        css = css.replace(
            'line-height: 1.5;',
            'line-height: 1.3;'
        )
        css = re.sub(
            r'margin-bottom:\s*[\d.]+pt;',
            'margin-bottom: 8pt;',
            css
        )
    
    # Divisor de secciones
    divider = pdf_config.get("section_divider", _DEFAULTS["section_divider"])
    if divider == "none":
        css = re.sub(
            r'section h2\s*\{[^}]*border-bottom:[^}]*\}',
            'section h2 { border-bottom: none; }',
            css
        )
    elif divider == "double":
        css = re.sub(
            r'border-bottom:\s*[\d.]+pt\s+solid\s+[^;]+;',
            'border-bottom: 3pt double;',
            css
        )
    elif divider == "dots":
        css = re.sub(
            r'border-bottom:\s*[\d.]+pt\s+solid\s+[^;]+;',
            'border-bottom: 2pt dotted;',
            css
        )
    
    # Estilo de cabecera
    header_style = pdf_config.get(
        "header_style", _DEFAULTS["header_style"])
    if header_style == "minimal":
        css = re.sub(
            r'\.header\s*\{[^}]*\}',
            '.header { border-bottom: none; padding-bottom: 4pt; margin-bottom: 8pt; }',
            css
        )
    elif header_style == "modern":
        css = re.sub(
            r'\.header\s*\{[^}]*\}',
            '.header { text-align: center; border-bottom: none; padding-bottom: 8pt; margin-bottom: 12pt; }',
            css
        )
    
    return css


def render_cv_html(content: dict, job: dict | None = None, pdf_config: dict | None = None) -> str:
    """Construye el HTML final. Lanza ValueError si queda vacio."""
    template = (_templates_dir() / "cv.html").read_text(encoding="utf-8")
    css = (_templates_dir() / "cv.css").read_text(encoding="utf-8")

    # Aplicar configuración de PDF si existe
    if pdf_config:
        css = _apply_pdf_config_to_css(css, pdf_config)

    # Linea de titulo: SOLO el titulo del perfil. El rol de la oferta
    # no se hace pasar por titulo propio: va en "Cargo objetivo".
    # Si el perfil no trae titulo, se marca en vez de inventarlo.
    adapted = str(content.get("target_role") or "").strip()
    own = str(content.get("title") or "").strip()
    professional_title = own or _missing_text("title")
    if adapted and adapted.lower() != own.lower() \
            and adapted.lower() not in own.lower():
        objective_line = f"Cargo objetivo: {adapted}"
    else:
        objective_line = ""

    cfg = pdf_config or {}
    show_links = cfg.get("show_links", True) not in (
        False, 0, "0", "false", "False")
    line1, line2 = _contact_lines(content, show_links=show_links)

    # Summary: del perfil (con o sin pulido LLM). Si falta, se marca.
    # profile_length recorta por oraciones (subconjunto, no reescritura).
    summary = ""
    if str(content.get("summary") or "").strip():
        summary = _section(
            "Perfil Profesional",
            f'<p class="summary">'
            f"{esc(_fit_profile_length(content.get('summary'), cfg.get('profile_length')))}</p>"
        )
    else:
        summary = _section(
            "Perfil Profesional", _missing_block(content, "summary"))

    # Orden de secciones desde pdf_config o default unico centralizado.
    # Slugs desconocidos se ignoran; quitar un slug oculta la seccion.
    # "certifications" vive dentro de "other_studies" (sin bloque propio).
    from app.adapt.defaults import DEFAULT_PDF_CONFIG as _DEFAULTS

    default_order = list(_DEFAULTS["section_order"])
    section_order = (pdf_config or {}).get("section_order") or default_order
    if not isinstance(section_order, list):
        section_order = default_order

    fmt = str((pdf_config or {}).get(
        "date_format", _DEFAULTS["date_format"]) or _DEFAULTS["date_format"])
    try:
        max_bullets = int(cfg.get("max_bullets", 0) or 0)
    except (TypeError, ValueError):
        max_bullets = 0
    show_soft = cfg.get("show_soft_skills", True) not in (
        False, 0, "0", "false", "False")
    show_courses = cfg.get("show_courses", True) not in (
        False, 0, "0", "false", "False")
    show_langs = cfg.get("show_languages", True) not in (
        False, 0, "0", "false", "False")
    blocks = {
        "summary": summary,
        "experience": _experience_block(content, fmt, max_bullets),
        "education": _education_block(content, fmt),
        "projects": _projects_block(content, fmt),
        "skills": _technical_skills_block(content),
        "soft_skills": _soft_skills_block(content) if show_soft else "",
        "languages": _languages_block(content) if show_langs else "",
        "other_studies": _other_studies_block(content, fmt)
        if show_courses else "",
        "other_knowledge": _other_knowledge_block(content),
    }

    titles = {
        "CSS": css,
        "FULL_NAME": esc(content.get("full_name")),
        "TITLE_LINE": esc(professional_title),
        "OBJECTIVE_LINE": esc(objective_line),
        "CONTACT_LINE_1": line1,
        "CONTACT_LINE_2": line2,
        "SECTIONS": "".join(
            blocks.get(slug, "") for slug in section_order
            if isinstance(slug, str)),
    }

    html_text = template
    for key, value in titles.items():
        html_text = html_text.replace("{{" + key + "}}", value)

    if not content.get("full_name") and "<section>" not in html_text:
        raise ValueError("Contenido insuficiente para generar el HTML.")

    return html_text