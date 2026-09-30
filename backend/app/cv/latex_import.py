"""Importador de CV en LaTeX a perfil estructurado.

Lee el .tex del usuario y extrae informacion personal, resumen,
educacion, experiencia, proyectos, skills, idiomas y certificaciones
hacia el formato del perfil modular (base_cv.json).

NO inventa nada: todo lo extraido viene literalmente del .tex.
Si una seccion no se reconoce, se reporta en warnings en vez de
adivinar. Ademas extrae el preambulo (paquetes/geometria/fuentes)
para futura adaptacion visual de la plantilla.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_SECTION_KINDS = (
    ("education", (
        "educacion", "educación", "formacion", "formación academica",
        "formación académica", "estudios", "education",
        "academic background",
    )),
    ("experience", (
        "experiencia", "experiencia laboral", "experiencia profesional",
        "work experience", "employment", "employment history",
        "professional experience",
    )),
    ("projects", (
        "proyectos", "projects", "proyectos personales",
        "proyectos academicos", "proyectos académicos",
        "personal projects", "side projects",
    )),
    ("skills", (
        "habilidades", "skills", "technical skills", "competencias",
        "conocimientos", "herramientas", "technologies", "technologies ",
        "tecnologias", "tecnologías",
    )),
    ("languages", (
        "idiomas", "languages",
    )),
    ("certifications", (
        "certificaciones", "certifications", "cursos", "courses",
        "certificados", "certificates", "capacitacion", "capacitación",
    )),
    ("summary", (
        "perfil", "resumen", "profile", "summary", "objetivo",
        "objective", "perfil profesional", "professional summary",
        "sobre mi", "about me",
    )),
)


def _strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        cleaned = []
        i = 0
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                break
            cleaned.append(line[i])
            i += 1
        out.append("".join(cleaned))
    return "\n".join(out)


def _clean_latex(text: str) -> str:
    """Quita comandos comunes y deja texto plano legible."""
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\url\{([^}]*)\}", r"\1", text)
    text = re.sub(
        r"\\(textbf|textit|textsc|textsl|emph|underline|large|Large|LARGE|"
        r"small|footnotesize|scriptsize|tiny|normalsize)\{([^}]*)\}",
        r"\2", text,
    )
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", text)
    text = text.replace("\\\\", " ").replace("\\", " ")
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip(" \n,;|-")


def _split_items(body: str) -> list[str]:
    """Divide un cuerpo en items (itemize/enumerate o lineas con bala)."""
    items = re.split(r"\\item\b", body)
    if len(items) > 1:
        return [_clean_latex(p) for p in items[1:] if _clean_latex(p)]
    lines = [
        _clean_latex(line)
        for line in re.split(r"\\\\|\n", body)
        if _clean_latex(line)
    ]
    # Evita falsos items de una sola linea larga: solo si hay 2+.
    if len(lines) >= 2:
        return lines
    if lines:
        # Listas en una sola linea separadas por comas ("a, b, c").
        parts = [p.strip(" .") for p in re.split(r"[,;]", lines[0])]
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            return parts
        return [lines[0]]
    return []


def _split_sections(body: str) -> list[tuple[str, str]]:
    r"""Devuelve [(titulo, cuerpo)] por cada \section / \section*."""
    pattern = re.compile(r"\\section\*?\{([^}]*)\}")
    matches = list(pattern.finditer(body))
    sections = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections.append((match.group(1).strip(), body[start:end]))
    return sections


def _classify_section(title: str) -> str | None:
    lowered = title.lower()
    for kind, keywords in _SECTION_KINDS:
        if any(keyword in lowered for keyword in keywords):
            return kind
    return None


def _extract_emails_phones_links(text: str) -> dict:
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    urls = re.findall(r"https?://[^\s}]+", text)
    phones = re.findall(r"\+?\d[\d .()-]{6,}\d", text)
    linkedin = next((u for u in urls if "linkedin" in u.lower()), "")
    github = next((u for u in urls if "github" in u.lower()), "")
    portfolio = next(
        (u for u in urls if "linkedin" not in u.lower() and "github" not in u.lower()),
        "",
    )
    return {
        "email": emails[0] if emails else "",
        "phone": phones[0].strip() if phones else "",
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
    }


def _is_dateish(header_clean: str) -> bool:
    """Encabezado que es (casi) solo una fecha: '2021 -- 2026'."""
    return bool(re.search(r"\d{4}", header_clean)) and len(header_clean) <= 32


def _split_bold_entries(body: str, fallback_title: str) -> list[tuple[str, str]]:
    """Divide un cuerpo en entradas por \\textbf{...} estructurales.

    Solo inicia entrada un \\textbf cuyo bloque siguiente contenga
    itemize o fecha, cuya misma linea traiga fecha, o cuyo siguiente
    \\textbf sea fecha (patron cargo -- empresa -- fecha). Los \\textbf
    de fecha se anexan a la entrada previa (periodo); el resto del
    texto suelto se anexa al cuerpo en curso. Todo copiado, nada
    inferido.
    """
    pattern = re.compile(r"\\textbf\{([^}]*)\}")
    matches = list(pattern.finditer(body))
    if not matches:
        return [(fallback_title, body)]
    pairs: list[tuple[str, str]] = []
    preface = body[:matches[0].start()].strip()
    current_title: str | None = None
    current_parts: list[str] = []
    if preface and _clean_latex(preface):
        pairs.append((fallback_title, preface))

    def flush() -> None:
        nonlocal current_title, current_parts
        if current_title is not None:
            pairs.append((current_title, "\n".join(current_parts)))
            current_title, current_parts = None, []

    for index, match in enumerate(matches):
        chunk_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        chunk = body[match.end():chunk_end]
        header = match.group(1).strip()
        header_clean = _clean_latex(header)
        line_start = body.rfind("\n", 0, match.start()) + 1
        at_line_start = not body[line_start:match.start()].strip(" \t")
        line_end = body.find("\n", match.end())
        line_rest = body[match.end():line_end if line_end >= 0 else len(body)]
        next_header = (matches[index + 1].group(1).strip()
                       if index + 1 < len(matches) else "")
        if _is_dateish(header_clean):
            if current_title is not None:
                current_parts.append(match.group(0) + chunk)
            elif pairs:
                title, prev_body = pairs[-1]
                pairs[-1] = (title, prev_body + "\n" + match.group(0) + chunk)
            else:
                current_title, current_parts = header, [chunk]
            continue
        starts_entry = (
            r"\begin{itemize}" in chunk
            or bool(re.search(r"\d{4}", chunk[:400]))
            or bool(re.search(r"\d{4}", line_rest[:120]))
            or _is_dateish(_clean_latex(next_header))
            or (
                at_line_start
                and len(header_clean) > 20
                and not header_clean.endswith(":")
                and current_title is not None
            )
        )
        # Etiqueta tipo "Responsabilidad General:" nunca inicia entrada
        # (su itemize pertenece a la entrada en curso).
        if header_clean.endswith(":") and not (
            bool(re.search(r"\d{4}", chunk[:400]))
            or bool(re.search(r"\d{4}", line_rest[:120]))
        ):
            starts_entry = False
        if starts_entry:
            flush()
            current_title, current_parts = header, [chunk]
        elif current_title is not None:
            current_parts.append(match.group(0) + chunk)
        elif pairs:
            title, prev_body = pairs[-1]
            pairs[-1] = (title, prev_body + "\n" + match.group(0) + chunk)
        else:
            current_title, current_parts = header, [chunk]
    flush()
    return pairs or [(fallback_title, body)]
def _parse_entry_block(title: str, body: str) -> dict:
    r"""Una entrada de experiencia/educacion/proyecto.

    El titulo del \subsection aporta cargo — empresa — periodo; el cuerpo
    aporta los bullets. Todo copiado del .tex, nada inferido.
    """
    items = [i for i in _split_items(body) if i.strip()]
    # Solo guion largo/corto especial, |, / o doble espacio separan
    # campos (el "-" simple con espacios puede ser un rango de fechas).
    parts = [p.strip() for p in re.split(r"\s+[—–|/]\s+|\s{2,}", title)
             if p.strip()]
    entry: dict = {
        "title": parts[0] if parts else _clean_latex(title),
        "company": parts[1] if len(parts) > 1 else "",
        "period": " — ".join(parts[2:]) if len(parts) > 2 else "",
        "bullets": items,
        "perspectives": [],
    }
    if not entry["period"]:
        for part in parts:
            if re.search(r"\d{4}", part):
                entry["period"] = part
                break
    if not entry["period"]:
        # La fecha puede venir en el cuerpo (ej. "\hfill 2021 -- 2026").
        date_match = re.search(
            r"(\d{4}\s*(?:--|–|—|a|al|to)\s*(?:\d{4}|Actualidad|actualidad|present|Present))",
            _clean_latex(body),
        )
        if date_match:
            entry["period"] = date_match.group(1)
    return entry


def _parse_skills_block(body: str) -> dict[str, list[str]]:
    """Agrupa por lineas 'Categoria: a, b, c' o lista plana -> tools."""
    groups: dict[str, list[str]] = {
        "programming": [], "data": [], "bi": [],
        "databases": [], "tools": [],
    }
    text = _clean_latex(body)
    categorized = False
    pending_cat = ""
    for line in re.split(r"\\\\|\n", body):
        clean = _clean_latex(line)
        if not clean:
            continue
        cat, items = "", []
        if ":" in clean:
            _cat, _, values = clean.partition(":")
            cat = _cat.strip().lower()
            items = [v.strip(" .") for v in re.split(r"[,;|/]", values)
                     if v.strip(" .")]
            if not items:
                # Etiqueta sola ("Lenguajes:"); los valores vienen despues.
                pending_cat = cat
                continue
            pending_cat = ""
        elif pending_cat:
            cat, items = pending_cat, [
                v.strip(" .") for v in re.split(r"[,;|/]", clean)
                if v.strip(" .")]
            pending_cat = ""
            if not items:
                continue
        else:
            continue
        if not items:
            continue
        categorized = True
        if any(k in cat for k in ("lenguaje", "language", "program",
                                  "codigo", "código")):
            groups["programming"].extend(items)
        elif any(k in cat for k in ("dato", "data", "anal", "ciencia")):
            groups["data"].extend(items)
        elif any(k in cat for k in ("bi", "inteligencia", "power",
                                    "tableau", "visual")):
            groups["bi"].extend(items)
        elif any(k in cat for k in ("base", "database", "sql", "dato")):
            groups["databases"].extend(items)
        else:
            groups["tools"].extend(items)
    if not categorized:
        # Lista plana sin categorias: todo a tools (origen honesto).
        flat: list[str] = []
        for line in re.split(r"\\\\|\n", body):
            flat.extend(
                v.strip(" .") for v in re.split(r"[,;|/]", _clean_latex(line))
                if v.strip(" .")
            )
        groups = {"programming": [], "data": [], "bi": [],
                  "databases": [], "tools": flat}
    for key in groups:
        seen: list[str] = []
        for item in groups[key]:
            if item and item not in seen:
                seen.append(item)
        groups[key] = seen
    # Items de mas de 60 caracteres son prosa, no skills: se recortan
    # para no contaminar matching ni la linea de habilidades del CV.
    for key in groups:
        groups[key] = [i for i in groups[key] if len(i) <= 60]
    return groups


def extract_preamble_style(tex: str) -> dict:
    """Tokens visuales del .tex original para futura adaptacion de la
    plantilla (paquetes, geometria, fuentes). Solo lectura."""
    head = tex.split(r"\begin{document}")[0] if r"\begin{document}" in tex else ""
    packages = re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", head)
    geometry = re.findall(r"\\geometry\{([^}]*)\}", head)
    fonts = re.findall(r"\\(setmainfont|setsansfont|setmonofont)\{([^}]*)\}", head)
    docclass = re.findall(r"\\documentclass(?:\[[^\]]*\])?\{([^}]*)\}", head)
    return {
        "document_class": docclass[0] if docclass else "",
        "packages": sorted({p.strip() for group in packages for p in group.split(",")}),
        "geometry": geometry[0] if geometry else "",
        "fonts": [f[1] for f in fonts],
    }


def parse_latex_profile(tex_text: str) -> dict:
    """Convierte un CV en LaTeX a perfil estructurado.

    Devuelve {"profile": {...}, "warnings": [...], "style": {...}}.
    """
    warnings: list[str] = []
    if not tex_text or not tex_text.strip():
        raise ValueError("Documento LaTeX vacio.")
    text = _strip_comments(tex_text)
    style = extract_preamble_style(tex_text)

    body = text.split(r"\begin{document}", 1)
    body_text = body[1] if len(body) > 1 else text
    # Header = todo antes del primer \section (nombre + contacto).
    first_section = re.search(r"\\section\*?\{", body_text)
    header_text = body_text[:first_section.start()] if first_section else body_text[:800]
    header_clean = _clean_latex(header_text)
    contact = _extract_emails_phones_links(header_text + " " + text[:2000])

    name = ""
    for line in header_clean.split("\n"):
        line = line.strip(" ,;|-")
        if len(line) >= 4 and "@" not in line and "http" not in line:
            name = line.split("\n")[0][:120]
            break

    profile: dict = {
        "personal": {
            "full_name": name,
            "title": "",
            "location": "",
            "email": contact["email"],
            "phone": contact["phone"],
            "linkedin": contact["linkedin"],
            "github": contact["github"],
            "portfolio": contact["portfolio"],
        },
        "professional_summary": "",
        "education": [],
        "experience": [],
        "projects": [],
        "skills": {"programming": [], "data": [], "bi": [],
                   "databases": [], "tools": []},
        "languages": [],
        "certifications": [],
    }

    sections = _split_sections(body_text)
    if not sections:
        warnings.append(
            "No se encontraron secciones \\section{}; se importo el texto "
            "como resumen sin clasificar."
        )
        profile["professional_summary"] = _clean_latex(body_text)[:2000]
        return {"profile": profile, "warnings": warnings, "style": style}

    for title, content in sections:
        kind = _classify_section(title)
        if kind is None:
            warnings.append(f"Seccion no reconocida (se omite): '{title}'.")
            continue
        if kind == "skills" and "blanda" in title.lower():
            warnings.append(
                f"Seccion '{title}' omitida de skills (prosa, no lista "
                "de habilidades)."
            )
            continue
        if kind == "summary":
            profile["professional_summary"] = _clean_latex(content)[:2000]
        elif kind == "skills":
            groups = _parse_skills_block(content)
            for key, items in groups.items():
                profile["skills"][key].extend(
                    i for i in items if i not in profile["skills"][key]
                )
        elif kind == "languages":
            profile["languages"] = _split_items(content)
        elif kind == "certifications":
            profile["certifications"] = _split_items(content)
        elif kind in ("experience", "education", "projects"):
            # Subsecciones = entradas; si no hay, cada \textbf{...}
            # destacado inicia una entrada.
            subs = re.split(r"\\subsection\*?\{([^}]*)\}", content)
            if len(subs) > 1:
                pairs = list(zip(subs[1::2], subs[2::2]))
            else:
                pairs = _split_bold_entries(content, title)
            for sub_title, sub_body in pairs:
                entry = _parse_entry_block(sub_title, sub_body)
                if kind == "projects":
                    entry = {
                        "name": entry["title"],
                        "description": " ".join(entry["bullets"]),
                        "technologies": [],
                    }
                elif kind == "education":
                    entry = {
                        "degree": entry["title"],
                        "institution": entry["company"],
                        "year": entry["period"],
                    }
                profile[kind].append(entry)

    if not name:
        warnings.append("No se detecto el nombre del candidato en el encabezado.")
    if not profile["experience"] and not profile["projects"]:
        warnings.append("No se detectaron experiencias ni proyectos.")
    return {"profile": profile, "warnings": warnings, "style": style}
