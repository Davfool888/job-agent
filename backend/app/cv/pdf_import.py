"""Importador de CV en PDF (texto) a perfil estructurado.

Lee el texto extraido del PDF (pypdf) y lo convierte al formato del
perfil modular, con las mismas garantias que el importador LaTeX:

- NO inventa nada: todo sale literalmente del documento.
- Divide el CV en secciones: personal, descripcion, experiencia
  laboral, educacion FORMAL, cursos, idiomas y proyectos.
- La educacion formal (tecnico, tecnologo, pregrado, maestria,
  doctorado...) NUNCA se mezcla con cursos/diplomados: van a
  `education` con `level` de catalogo vs `certifications`.
- Una sola descripcion por experiencia/educacion (parrafos unidos).
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Encabezado normalizado -> tipo de seccion. Orden: claves largas
# primero para que "otros estudios" no caiga en "estudios".
_SECTION_KINDS: list[tuple[str, tuple[str, ...]]] = [
    ("summary", ("perfil profesional", "resumen profesional", "perfil",
                 "resumen", "profile", "summary", "objetivo", "sobre mi")),
    ("skills", ("competencias tecnicas", "habilidades tecnicas",
                "conocimientos tecnicos", "technical skills", "tecnologias",
                "herramientas", "competencias", "conocimientos")),
    ("soft_skills", ("habilidades blandas", "soft skills",
                     "competencias blandas")),
    ("experience", ("experiencia profesional", "experiencia laboral",
                    "work experience", "professional experience",
                    "employment history", "experiencia")),
    ("projects", ("proyectos destacados", "proyectos personales",
                  "proyectos academicos", "proyectos", "projects")),
    ("education", ("educacion", "formacion academica", "education",
                   "academic background", "estudios universitarios",
                   "estudios superiores")),
    ("certifications", ("otros estudios", "cursos y certificaciones",
                        "certificaciones", "cursos", "courses",
                        "certificates", "capacitacion", "otros cursos",
                        "formacion complementaria")),
    ("languages", ("idiomas", "languages", "lenguas")),
    ("other_knowledge", ("otros conocimientos", "conocimientos adicionales",
                         "informacion adicional")),
]

# Titulo normalizado -> id de EDUCATION_LEVELS (catalogs).
_LEVEL_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("phd", ("doctorado", "phd", "ph.d")),
    ("master", ("maestria", "magister", "mba", "master")),
    ("specialization", ("especializacion", "especialista",
                        "postgrado", "posgrado")),
    ("bachelor", ("ingenieria", "pregrado", "profesional",
                  "universitario", "licenciatura", "carrera",
                  "administracion", "contaduria", "derecho",
                  "medicina", "enfermeria", "arquitectura",
                  "diseno", "psicologia", "economia")),
    ("technologist", ("tecnologo", "tecnologa")),
    ("technical", ("tecnico", "tecnica")),
    ("high_school", ("bachiller", "secundaria", "colegio")),
    ("language", ("ingles", "english", "idioma", "language",
                  "frances", "portugues", "aleman", "italiano")),
    ("course", ("curso", "diplomado", "certificacion", "seminario",
                "taller", "bootcamp", "fundamentos de")),
]

_MONTHS = {
    "ene": 1, "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4, "may": 5, "mayo": 5, "jun": 6, "junio": 6,
    "jul": 7, "julio": 7, "ago": 8, "agosto": 8, "sep": 9,
    "septiembre": 9, "set": 9, "oct": 10, "octubre": 10, "nov": 11,
    "noviembre": 11, "dic": 12, "diciembre": 12,
    "jan": 1, "febr": 2, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_RANGE = re.compile(
    r"([A-Za-záéíóúñÁÉÍÓÚÑ]{3,}\s+\d{4}|\d{4})\s*[–—-]\s*"
    r"([A-Za-záéíóúñÁÉÍÓÚÑ]+\s*(?:\d{4})?|Actualidad|actualidad"
    r"|Actual|actual|present|Present|\d{4})"
)
_BULLET = re.compile(r"^[\s]*[■▪●•\-\*·oO]\s+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\+?\d[\d .()-]{6,}\d")
_LEVEL_TOKEN = re.compile(r"\b(A1|A2|B1|B2|C1|C2|Nativo|nativo)\b")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def _clean_line(line: str) -> str:
    line = _BULLET.sub("", line or "").strip()
    return re.sub(r"\s+", " ", line).strip()


def _join_wrapped(raw_lines: list[str]) -> list[str]:
    """Une lineas envueltas del PDF: una linea sin ':' que sigue a otra
    sin punto final es continuacion, no un item nuevo."""
    out: list[str] = []
    for raw in raw_lines:
        line = _clean_line(raw)
        if not line:
            continue
        if out and ":" not in line and not re.search(r"[.:;]$", out[-1]):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out
    line = _BULLET.sub("", line or "").strip()
    return re.sub(r"\s+", " ", line).strip()


def _classify_section(title: str) -> str | None:
    """Solo coincidencia exacta (normalizada), con sufijo ' / ...'.

    A proposito SIN containment: una linea del cuerpo como
    'Desarrollo Backend (proyectos personales): ...' jamas debe
    partir la seccion en dos. Y una linea con ':' + contenido
    ('Herramientas: Git, ...') es un item, nunca un encabezado.
    """
    lowered = _norm(title)
    if ":" in lowered:
        # 'Etiqueta: items' es un item, nunca un encabezado.
        return None
    for kind, keys in _SECTION_KINDS:
        for key in keys:
            if lowered == key or lowered.startswith(key + " /") \
                    or lowered.startswith(key + " -"):
                return kind
    return None


def _split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Cabecera (antes del primer titulo) + [(titulo, lineas)]."""
    header: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and _classify_section(stripped) and len(stripped) <= 90:
            if current_title is not None:
                sections.append((current_title, current))
            current_title, current = stripped, []
        elif current_title is None:
            if stripped:
                header.append(stripped)
        else:
            current.append(line)
    if current_title is not None:
        sections.append((current_title, current))
    return header, sections


def _extract_links(text: str) -> dict:
    emails = _EMAIL.findall(text)
    phones = _PHONE.findall(text)
    bare = re.findall(
        r"(?<![\w/@])((?:[a-z0-9-]+\.)+(?:com|co|dev|app|io|net|org)"
        r"(?:/[^\s|]*)?)", text, re.IGNORECASE)
    urls = re.findall(r"https?://[^\s|]+", text)
    candidates = [u.rstrip(".,;)") for u in urls]
    candidates += ["https://" + b.rstrip(".,;)") for b in bare]
    linkedin = next((u for u in candidates if "linkedin" in u.lower()), "")
    github = next((u for u in candidates if "github" in u.lower()), "")
    portfolio = next(
        (u for u in candidates
         if "linkedin" not in u.lower() and "github" not in u.lower()), "")
    phone = ""
    for raw in phones:
        digits = re.sub(r"\D", "", raw)
        if 7 <= len(digits) <= 15:
            phone = raw.strip()
            break
    return {
        "email": emails[0] if emails else "",
        "phone": phone,
        "linkedin": linkedin,
        "github": github,
        "portfolio": portfolio,
    }


def _parse_header(header: list[str]) -> dict:
    contact = _extract_links(" ".join(header))
    name = header[0] if header else ""
    title, location = "", ""
    for line in header[1:]:
        if "|" in line and not title:
            title = line.split("|")[0].strip()
        elif "|" in line:
            for part in [p.strip() for p in line.split("|")]:
                if not location and ("@" not in part
                                     and not re.search(r"\d{4,}", part)
                                     and "http" not in part
                                     and ".com" not in part
                                     and ".dev" not in part
                                     and ".app" not in part):
                    from app.profile import catalogs as _catalogs

                    if _catalogs.norm_city(part):
                        location = part
                        break
    return {"full_name": name, "title": title, "location": location,
            **contact}


def _month_start(token: str) -> str | None:
    token = token.strip()
    match = re.match(r"^([A-Za-záéíóúñÁÉÍÓÚÑ]+)\s+(\d{4})$", token)
    if match:
        month = _MONTHS.get(_norm(match.group(1))[:10])
        month = month or _MONTHS.get(_norm(match.group(1))[:3])
        if month:
            return f"{int(match.group(2)):04d}-{month:02d}-01"
        return None
    if re.match(r"^\d{4}$", token):
        return f"{token}-01-01"
    return None


def _parse_range(line: str) -> tuple[str | None, str | None, bool]:
    """(inicio_iso, fin_iso, es_actual). Solo meses/años explicitos."""
    match = _DATE_RANGE.search(line)
    if not match:
        return None, None, False
    start = _month_start(match.group(1))
    end_token = match.group(2).strip()
    if _norm(end_token) in ("actualidad", "actual", "present",
                            "presente", "actualmente"):
        return start, None, True
    return start, _month_start(end_token), False


def _looks_like_org(line: str) -> bool:
    if not line or len(line) > 120:
        return False
    if "–" in line or "—" in line or "|" in line:
        return True
    if "," in line:
        from app.profile import catalogs as _catalogs

        tail = line.split(",")[-1]
        if _catalogs.norm_city(tail) or _catalogs.norm_city(line):
            return True
    return len(line) <= 80 and not line.endswith(".")


def _split_org(line: str) -> tuple[str, str]:
    for sep in ("–", "—", "|"):
        if sep in line:
            parts = [p.strip() for p in line.split(sep) if p.strip()]
            if len(parts) >= 2:
                return parts[0], sep.join(parts[1:]).strip(" -,")
    if " - " in line:
        # Guion simple solo con espacios (no partir "USD-COP", "X-Ray").
        head, _, tail = line.partition(" - ")
        from app.profile import catalogs as _catalogs

        if _catalogs.norm_city(tail) or _catalogs.norm_city(line):
            return head.strip(), line.strip()
    if "," in line:
        head, _, tail = line.rpartition(",")
        from app.profile import catalogs as _catalogs

        if _catalogs.norm_city(tail) or _catalogs.norm_city(line):
            return head.strip(), line.strip()
    return line.strip(), ""


def _title_before_date(lines: list[str], date_idx: int,
                       block_start: int) -> int:
    """Inicio del titulo: la linea justo antes de la fecha, mas como
    maximo una anterior si parece continuacion del titulo (no vacia,
    corta, sin punto final). La descripcion previa termina ahi."""
    start = max(date_idx - 1, block_start)
    prev = lines[start - 1].strip() if start - 1 >= block_start else ""
    if prev and len(prev) <= 100 \
            and not prev.endswith((".", ":", ";", ",")):
        start -= 1
    return start


def _split_dated_entries(raw_lines: list[str]) -> list[dict]:
    """Entradas delimitadas por lineas de rango de fechas.

    Estructura por entrada: titulo (antes), fecha, organizacion
    (despues), descripcion = resto unido en un solo texto.
    """
    lines = [_clean_line(l) for l in raw_lines]
    date_idx = [i for i, l in enumerate(lines) if _DATE_RANGE.search(l)]
    title_starts = [_title_before_date(lines, d, 0) for d in date_idx]
    entries: list[dict] = []
    pos = 0
    for n, d in enumerate(date_idx):
        t_start = max(title_starts[n], pos)
        title = " ".join(lines[t_start:d]).strip()
        start, end, current = _parse_range(lines[d])
        org_line = lines[d + 1] if d + 1 < len(lines) else ""
        if _looks_like_org(org_line):
            company, city = _split_org(org_line)
            desc_from = d + 2
        else:
            company, city = "", ""
            desc_from = d + 1
        desc_end = title_starts[n + 1] if n + 1 < len(date_idx) else len(lines)
        desc_lines = lines[desc_from:desc_end]
        pos = desc_end
        description = " ".join(l for l in desc_lines if l).strip()
        entries.append({
            "title": title, "company": company, "city": city,
            "start_date": start, "end_date": end,
            "is_current": current, "description": description,
        })
    return entries


def _classify_level(title: str, institution: str = "") -> str:
    text = _norm(f"{title} {institution}")
    for level_id, keywords in _LEVEL_KEYWORDS:
        if any(k in text for k in keywords):
            return level_id
    return "other"


def _is_institution_group(line: str) -> re.Match | None:
    """'Platzi – 2021 – 2026' / 'Academia – 2025 – Actualidad'."""
    return re.match(
        r"^(.+?)\s*[–—-]\s*(\d{4})\s*[–—-]\s*"
        r"(\d{4}|Actualidad|actualidad|Actual|actual)$", line.strip())


def _parse_certifications(raw_lines: list[str],
                          warnings: list[str]) -> tuple[list[dict], list[dict]]:
    """Cursos -> certifications; idioma detectado -> languages.

    Todo lo que no sea curso ni idioma se omite con warning (nunca se
    fuerza a una seccion equivocada).
    """
    from app.profile import catalogs as _catalogs

    lines = [_clean_line(l) for l in raw_lines if _clean_line(l)]
    certs: list[dict] = []
    langs: list[dict] = []
    institution = ""
    group_desc_pending = False
    for line in lines:
        group = _is_institution_group(line)
        if group:
            institution = group.group(1).strip()
            group_desc_pending = True
            continue
        lang = _catalogs.norm_language(line.split("–")[0].split("-")[0])
        level_match = _LEVEL_TOKEN.search(line)
        if lang and level_match and len(line) <= 120:
            # Sin desglose por habilidad: el nivel general aplica a
            # todas (listening/reading/writing/speaking).
            level = _catalogs.norm_language_level(level_match.group(1))
            langs.append({
                "id": lang["id"], "language": lang["id"],
                "language_label": lang["label"], "academy": institution,
                "level": level, "listening": level, "reading": level,
                "writing": level, "speaking": level,
            })
            group_desc_pending = False
            continue
        lowered = _norm(line)
        starts_course = lowered.startswith(
            ("curso", "diplomado", "certific", "seminario", "taller",
             "bootcamp")) or "fundamentos de" in lowered
        dated = re.match(
            r"^(.+?)\s*[–—-]\s*(.+?)\s*[–—-]\s*(\d{4})$", line)
        if dated and not group_desc_pending and len(line) <= 140:
            # 'Python for Everybody – Coursera – 2022': curso con
            # institucion y año explicitos en la misma linea.
            from app.profile.schema import normalize_date as _ndate

            certs.append({"name": dated.group(1).strip(),
                          "institution": dated.group(2).strip(),
                          "issued_date": _ndate(dated.group(3)),
                          "expiry_date": None, "credential_id": "",
                          "credential_url": "", "description": ""})
            continue
        if starts_course or (institution and not group_desc_pending
                             and len(line) <= 140):
            certs.append({"name": line, "institution": institution,
                          "issued_date": None, "expiry_date": None,
                          "credential_id": "", "credential_url": "",
                          "description": ""})
            group_desc_pending = False
        elif group_desc_pending and (line.endswith(".") or len(line) > 100):
            group_desc_pending = False  # parrafo del grupo, se omite
        else:
            warnings.append(f"Linea de estudios sin clasificar: '{line[:80]}'.")
            group_desc_pending = False
    return certs, langs


def _parse_languages_block(raw_lines: list[str]) -> list[dict]:
    from app.profile import catalogs as _catalogs

    langs: list[dict] = []
    for raw in raw_lines:
        line = _clean_line(raw)
        if not line:
            continue
        head = re.split(r"[–—\-:|]", line)[0]
        lang = _catalogs.norm_language(head)
        if not lang:
            continue
        level_match = _LEVEL_TOKEN.search(line)
        level = _catalogs.norm_language_level(
            level_match.group(1)) if level_match else None
        langs.append({
            "id": lang["id"], "language": lang["id"],
            "language_label": lang["label"], "academy": "",
            "level": level, "listening": level, "reading": level,
            "writing": level, "speaking": level,
        })
    return langs


_TECH_VOCAB: list[str] = []
_TECH_CANON: dict[str, str] = {}


def _tech_vocab() -> tuple[list[str], dict[str, str]]:
    global _TECH_VOCAB, _TECH_CANON
    if _TECH_VOCAB:
        return _TECH_VOCAB, _TECH_CANON
    from app.analysis import signals as _signals

    canon: dict[str, str] = {}
    for label, variants, _ in _signals.SKILLS:
        for variant in [label, *variants]:
            key = _norm(variant)
            if key and key not in canon:
                canon[key] = label
    for tool in _signals.TOOLS:
        key = _norm(tool)
        if key and key not in canon:
            canon[key] = tool.strip().upper() if len(tool.strip()) <= 4 \
                else tool.strip().title()
    for extra in ("YOLOv8", "OpenCV", "Roboflow", "Scikit-learn",
                  "Google Colab", "Google Apps Script", "MariaDB",
                  "PostgreSQL", "SQLite", "MongoDB", "MySQL", "Linux",
                  "WSL", "Visual Studio Code", "GitHub", "Flask",
                  "FastAPI", "JavaScript", "Power Query", "Excel",
                  "CLI", "REST APIs", "API"):
        key = _norm(extra)
        if key and key not in canon:
            canon[key] = extra
    vocab = sorted(canon, key=len, reverse=True)
    _TECH_VOCAB, _TECH_CANON = vocab, canon
    return vocab, canon


def _extract_technologies(text: str) -> list[str]:
    vocab, canon = _tech_vocab()
    lowered = _norm(f" {text} ")
    found: list[str] = []
    for token in vocab:
        if len(token) <= 2:
            continue
        if re.search(rf"(?<![a-záéíóúñ]){re.escape(token)}(?![a-záéíóúñ])",
                     lowered):
            label = canon[token]
            if label not in found:
                found.append(label)
    return found


def _split_projects(raw_lines: list[str]) -> list[dict]:
    lines = [_clean_line(l) for l in raw_lines if _clean_line(l)]
    entries: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        # Titulo: corto, sin puntuacion interna de cierre, seguido de
        # texto mas largo (o minuscula inicial). Las lineas de
        # descripcion con comas/puntos nunca califican.
        is_title = (
            len(line) <= 100
            and not re.search(r"[.,:;]", line)
            and bool(nxt) and (len(nxt) > 40 or (nxt and nxt[0].islower()))
        )
        if is_title:
            j = i + 1
            desc: list[str] = []
            while j < len(lines):
                candidate, following = lines[j], (
                    lines[j + 1] if j + 1 < len(lines) else "")
                if (len(candidate) <= 100
                        and not re.search(r"[.,:;]", candidate)
                        and following
                        and (len(following) > 40
                             or (following and following[0].islower()))):
                    break
                desc.append(candidate)
                j += 1
            description = " ".join(desc).strip()
            entries.append({
                "name": line,
                "description": description,
                "technologies": _extract_technologies(
                    f"{line} {description}"),
                "url": "", "repo": "",
            })
            i = j
        else:
            i += 1
    return entries


_SKILL_GROUPS = (
    ("programming", ("lenguaje", "program", "codigo", "desarrollo")),
    ("data", ("dato", "anal", "ciencia", "estadist")),
    ("bi", ("bi", "inteligencia", "power", "tableau", "visual",
            "dashboard", "kpi", "reporte")),
    ("databases", ("base", "database", "sql", "mongo")),
)

# Blanda canonica -> raices que la evidencian en una descripcion.
# Raices cortas (<6) exigen palabra completa (+plural); largas van
# por subcadena. Todo sale del texto, nada se inventa.
_SOFT_TRIGGERS: list[tuple[str, tuple[str, ...]]] = [
    ("Trabajo en equipo", ("equipo", "colabor", "trabajo en equipo")),
    ("Comunicación", ("comunic",)),
    ("Liderazgo", ("lider", "dirigir", "supervis", "a cargo")),
    ("Orientación a resultados", ("objetivo", "resultado", "meta",
                                  "indicador", "cumplimiento")),
    ("Atención al detalle", ("detalle", "validar", "revisar",
                             "calidad", "verificar")),
    ("Pensamiento analítico", ("análisis", "analizar", "interpretar")),
    ("Resolución de problemas", ("problema", "solución", "resolver")),
    ("Adaptabilidad", ("adapt",)),
    ("Gestión del tiempo", ("plazo", "cronograma", "priorizar",
                            "seguimiento")),
]


def _extract_soft_skills(text: str, limit: int = 6) -> list[str]:
    lowered = _norm(f" {text} ")
    found: list[str] = []
    for label, stems in _SOFT_TRIGGERS:
        for stem in stems:
            stem = _norm(stem)
            if len(stem) < 6:
                hit = re.search(
                    rf"(?<![a-záéíóúñ]){re.escape(stem)}(s|es)?"
                    r"(?![a-záéíóúñ])", lowered)
            else:
                hit = stem in lowered
            if hit:
                if label not in found:
                    found.append(label)
                break
        if len(found) >= limit:
            break
    return found


def _parse_skills_block(raw_lines: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "programming": [], "data": [], "bi": [],
        "databases": [], "tools": [],
    }
    for line in _join_wrapped(raw_lines):
        if ":" not in line:
            continue
        cat, _, values = line.partition(":")
        items = [v.strip(" .") for v in re.split(r"[,;|/]", values)
                 if v.strip(" .")]
        items = [v for v in items if len(v) <= 60]
        if not items:
            continue
        lowered = _norm(cat)
        if any(k in lowered for k in ("lenguaje", "program", "codigo")):
            groups["programming"].extend(items)
        elif any(k in lowered for k in ("base", "database")):
            groups["databases"].extend(items)
        elif any(k in lowered for k in ("dato", "anal", "ciencia")):
            groups["data"].extend(items)
        elif any(k in lowered for k in ("bi", "inteligencia", "power",
                                        "tableau", "visual")):
            if "base" in lowered or "database" in lowered:
                groups["databases"].extend(items)
            else:
                groups["bi"].extend(items)
        elif any(k in lowered for k in ("base", "database")):
            groups["databases"].extend(items)
        else:
            groups["tools"].extend(items)
    for key in groups:
        seen: list[str] = []
        try:
            from app.analysis.skills_canonical import normalize_skill_list

            groups[key] = normalize_skill_list(groups[key], limit=100)
            continue
        except Exception:  # noqa: BLE001
            pass
        for item in groups[key]:
            if item and item not in seen:
                seen.append(item)
        groups[key] = seen
    return groups


def extract_pdf_text(content: bytes) -> str:
    """Texto plano del PDF. Lanza ValueError si es ilegible."""
    from pypdf import PdfReader
    import io as _io

    try:
        reader = PdfReader(_io.BytesIO(content))
        parts = [(page.extract_text() or "") for page in reader.pages]
    except Exception as error:
        raise ValueError(f"No se pudo leer el PDF: {error}")
    text = "\n".join(p.strip() for p in parts if p and p.strip()).strip()
    if len(text) < 50:
        raise ValueError(
            "El PDF no tiene texto extraible (¿escaneado como imagen?).")
    return text


def parse_pdf_profile(text: str) -> dict:
    """Texto del CV -> {"profile", "warnings"} (perfil estructurado)."""
    from app.profile import schema as profile_schema

    warnings: list[str] = []
    if not text or not text.strip():
        raise ValueError("Documento vacio.")
    lines = [l.rstrip() for l in text.splitlines()]
    header, sections = _split_sections(lines)
    personal_raw = _parse_header(header)

    profile: dict = {
        "personal": {
            "first_name": "", "last_name": "",
            "full_name": personal_raw["full_name"],
            "title": personal_raw["title"],
            "location": personal_raw["location"],
            "email": personal_raw["email"],
            "secondary_email": "",
            "phone": personal_raw["phone"],
            "secondary_phone": "",
            "linkedin": personal_raw["linkedin"],
            "github": personal_raw["github"],
            "portfolio": personal_raw["portfolio"],
            "address": "",
        },
        "professional_summary": "",
        "years_experience": None,
        "technical_skills": [],
        "soft_skills": [],
        "education": [],
        "experience": [],
        "projects": [],
        "skills": {"programming": [], "data": [], "bi": [],
                   "databases": [], "tools": []},
        "languages": [],
        "certifications": [],
    }

    for title, body in sections:
        kind = _classify_section(title)
        if kind is None:
            warnings.append(f"Seccion no reconocida (se omite): '{title}'.")
            continue
        if kind == "summary":
            profile["professional_summary"] = " ".join(
                _clean_line(l) for l in body if _clean_line(l))[:2000]
        elif kind == "skills":
            groups = _parse_skills_block(body)
            for key, items in groups.items():
                profile["skills"][key].extend(
                    i for i in items if i not in profile["skills"][key])
        elif kind == "soft_skills":
            for line in _join_wrapped(body):
                label = line.split(":")[0].strip().rstrip(".")
                if label and len(label) <= 60 \
                        and label not in profile["soft_skills"]:
                    profile["soft_skills"].append(label)
        elif kind == "other_knowledge":
            for raw in body:
                line = _clean_line(raw)
                if ":" in line:
                    _, _, values = line.partition(":")
                    for item in re.split(r"[,;|]", values):
                        item = item.strip(" .")
                        if item and len(item) <= 60 \
                                and item not in profile["skills"]["tools"]:
                            profile["skills"]["tools"].append(item)
        elif kind == "languages":
            profile["languages"].extend(_parse_languages_block(body))
        elif kind == "experience":
            for entry in _split_dated_entries(body):
                tech = _extract_technologies(
                    f"{entry['title']} {entry['description']}")[:20]
                profile["experience"].append({
                    "title": entry["title"],
                    "company": entry["company"],
                    "city": entry["city"] or None,
                    "start_date": entry["start_date"],
                    "end_date": entry["end_date"],
                    "is_current": entry["is_current"],
                    "modality": None,
                    "description": entry["description"],
                    "technical_skills": tech,
                    "soft_skills": _extract_soft_skills(
                        entry["description"]),
                    "contract_type": ("Prácticas" if re.search(
                        r"practic", entry["title"], re.IGNORECASE)
                        else None),
                })
        elif kind == "education":
            for entry in _split_dated_entries(body):
                level = _classify_level(entry["title"], entry["company"])
                if level in ("course", "language", "other"):
                    warnings.append(
                        f"'{entry['title'][:60]}' en Educacion no parece "
                        f"formacion formal; se guarda como Otro.")
                    if level == "other":
                        level = "other"
                profile["education"].append({
                    "degree": entry["title"],
                    "institution": entry["company"],
                    "level": level,
                    "start_date": entry["start_date"],
                    "end_date": entry["end_date"],
                    "status": ("in_progress" if entry["is_current"]
                               or (entry["end_date"] or "")[:4] >= "2026"
                               else "finished"),
                    "description": entry["description"],
                })
        elif kind == "projects":
            profile["projects"].extend(_split_projects(body))
        elif kind == "certifications":
            certs, langs = _parse_certifications(body, warnings)
            profile["certifications"].extend(certs)
            profile["languages"].extend(langs)

    flat: list[str] = []
    for key in ("programming", "data", "bi", "databases", "tools"):
        flat.extend(i for i in profile["skills"][key] if i not in flat)
    try:
        from app.analysis.skills_canonical import normalize_skill_list

        profile["technical_skills"] = normalize_skill_list(flat, limit=100)
        profile["soft_skills"] = normalize_skill_list(
            profile.get("soft_skills") or [], limit=50
        )
    except Exception:  # noqa: BLE001
        profile["technical_skills"] = flat

    starts = [e["start_date"] for e in profile["experience"]
              if e.get("start_date")]
    ends = [e["end_date"] for e in profile["experience"]
            if e.get("end_date")]
    if starts:
        from datetime import date as _date

        s_min = min(starts)
        s_max = max(ends) if ends else s_min
        try:
            years = (int(s_max[:4]) - int(s_min[:4])
                     + (int(s_max[5:7]) - int(s_min[5:7])) / 12)
            profile["years_experience"] = round(max(years, 0), 1)
            warnings.append(
                f"years_experience={profile['years_experience']} calculado "
                f"del rango {s_min[:7]}–{s_max[:7]}; ajustalo si no aplica.")
        except (ValueError, IndexError):
            pass

    if not personal_raw["full_name"]:
        warnings.append("No se detecto el nombre en el encabezado.")
    if not profile["experience"]:
        warnings.append("No se detecto experiencia laboral.")
    if not profile["education"]:
        warnings.append("No se detecto educacion formal.")

    normalized, schema_warnings = profile_schema.normalize_rich_profile(
        profile)
    warnings.extend(schema_warnings)
    return {"profile": normalized, "warnings": warnings}
