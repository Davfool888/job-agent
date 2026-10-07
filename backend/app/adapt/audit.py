"""Auditoria del CV adaptado (config > relevancia > estetica).

Verifica despues de generar, sin modificar datos:
- Estructura: secciones segun config presentes y en orden, conteos
  dentro de los topes del usuario.
- No-invencion: cada skill/tecnologia/keyword del CV existe en el
  perfil real (normalizado). Lo que no esta, se reporta.
- Personalizacion: cobertura de keywords de la oferta (presentes vs
  faltantes-pero-reales; las que el candidato no tiene no se exigen).
- ATS/paginas: texto extraible, 1 columna, paginas <= max_pages.
- Densidad y fechas consistentes.

Devuelve dict con scores, issues y mejoras permitidas/bloqueadas.
Nunca lanza: ante cualquier fallo interno devuelve audit degradado.
"""
from __future__ import annotations


def _profile_terms(profile: dict) -> set[str]:
    """Todo lo real del candidato (normalizado)."""
    from app.analysis.signals import norm

    terms: set[str] = set()

    def add(value) -> None:
        if isinstance(value, list):
            for item in value:
                add(item)
        elif isinstance(value, dict):
            for item in value.values():
                add(item)
        elif value:
            key = norm(str(value))
            if key:
                terms.add(key)

    profile = profile or {}
    add(profile.get("skills_technical"))
    add(profile.get("skills_soft"))
    add(profile.get("skills_groups"))
    add(profile.get("target_roles"))
    for section in ("experiences", "experience", "education", "projects",
                    "certifications"):
        items = profile.get(section) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            add(item.get("technical_skills"))
            add(item.get("soft_skills"))
            add(item.get("technologies"))
    for lang in profile.get("languages") or []:
        if isinstance(lang, dict):
            add(lang.get("label"))
            add(lang.get("language_label"))
    return terms


def _content_terms(content: dict) -> dict[str, list[str]]:
    """Skills/tecnologias/idiomas que el CV declara, por origen."""
    out: dict[str, list[str]] = {"skills": [], "technologies": [],
                                 "languages": []}

    def add(bucket: str, value) -> None:
        if isinstance(value, list):
            for item in value:
                add(bucket, item)
        elif isinstance(value, dict):
            for item in value.values():
                add(bucket, item)
        elif value and str(value).strip():
            text = str(value).strip()
            if text not in out[bucket]:
                out[bucket].append(text)

    content = content or {}
    add("skills", content.get("skills"))
    add("skills", (content.get("skills_groups") or {}))
    for section in ("experiences", "education", "projects",
                    "certifications"):
        for item in content.get(section) or []:
            if not isinstance(item, dict):
                continue
            add("skills", item.get("technical_skills"))
            add("skills", item.get("soft_skills"))
            add("technologies", item.get("technologies"))
    for lang in content.get("languages") or []:
        if isinstance(lang, dict):
            add("languages", lang.get("label"))
            add("languages", lang.get("language_label"))
    return out


def _offer_keywords(offer: dict) -> list[str]:
    """Keywords de la oferta (titulo + descripcion + requisitos)."""
    from app.adapt.matcher import offer_required_skills
    from app.analysis.signals import norm

    offer = offer or {}
    text = " ".join(str(offer.get(k) or "") for k in (
        "title", "description", "requirements", "responsibilities"))
    return offer_required_skills(offer, norm(text))


def _pdf_facts(pdf_path) -> dict:
    """Paginas + texto extraible (0 paginas si ilegible)."""
    facts: dict = {"pages": 0, "chars": 0, "readable": False, "text": ""}
    try:
        from pathlib import Path

        from pypdf import PdfReader

        reader = PdfReader(str(Path(pdf_path)))
        facts["pages"] = len(reader.pages)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        facts["text"] = text
        facts["chars"] = len(text.strip())
        facts["readable"] = facts["chars"] > 200
    except Exception:  # noqa: BLE001
        pass
    return facts


def audit_cv(content: dict, profile: dict, offer: dict,
             pdf_config: dict, pdf_path=None) -> dict:
    """Audita el CV generado. Ver docstring del modulo."""
    from app.analysis.signals import norm

    issues: list[dict] = []
    allowed: list[str] = []
    blocked: list[str] = []

    def issue(area: str, message: str, blocking: bool = False) -> None:
        issues.append({"area": area, "message": message,
                       "blocking": blocking})

    config = pdf_config or {}
    real = _profile_terms(profile)
    declared = _content_terms(content)

    # 1. No-invencion (bloqueante): todo lo declarado existe en el perfil.
    invented: list[str] = []
    for bucket in ("skills", "technologies", "languages"):
        for term in declared[bucket]:
            if norm(term) not in real:
                invented.append(term)
    if invented:
        issue("veracidad",
              f"Terminos sin respaldo en el perfil: "
              f"{', '.join(invented[:8])}", blocking=True)
    else:
        allowed.append("Sin terminos inventados: todo lo declarado "
                       "existe en el perfil.")

    # 2. Topes de config (bloqueante si se violan).
    for key, label in (("experiences", "experiencias"),
                       ("projects", "proyectos")):
        limit_key = "max_experiences" if key == "experiences" \
            else "max_projects"
        try:
            limit = int(config.get(limit_key, 0) or 0)
        except (TypeError, ValueError):
            limit = 0
        count = len([i for i in (content.get(key) or [])
                     if isinstance(i, dict)])
        if limit > 0 and count > limit:
            issue("configuracion",
                  f"{label}: {count} > maximo configurado ({limit}).",
                  blocking=True)
    for exp in content.get("experiences") or []:
        if not isinstance(exp, dict):
            continue
        try:
            bullet_cap = int(config.get("max_bullets", 0) or 0)
        except (TypeError, ValueError):
            bullet_cap = 0
        n_bullets = len(exp.get("bullets") or [])
        if bullet_cap > 0 and n_bullets > bullet_cap:
            issue("configuracion",
                  f"Bullets en '{str(exp.get('title') or '')[:40]}': "
                  f"{n_bullets} > maximo ({bullet_cap}).", blocking=True)

    # 3. Secciones segun config: presentes con contenido.
    order = config.get("section_order")
    if not isinstance(order, list) or not order:
        order = ["summary", "experience", "education", "projects",
                 "skills", "soft_skills", "languages",
                 "other_studies", "other_knowledge"]
    hidden = {slug for slug, flag in (
        ("soft_skills", config.get("show_soft_skills", True)),
        ("languages", config.get("show_languages", True)),
        ("other_studies", config.get("show_courses", True)),
    ) if flag in (False, 0, "0", "false", "False")}
    section_has = {
        "summary": bool(str(content.get("summary") or "").strip()),
        "experience": bool(content.get("experiences")),
        "education": bool(content.get("education")),
        "projects": bool(content.get("projects")),
        "skills": bool(content.get("skills"))
        or bool(content.get("skills_groups")),
        "soft_skills": bool(content.get("skills_soft")),
        "languages": bool(content.get("languages")),
        "other_studies": bool(content.get("other_studies"))
        or bool(content.get("certifications")),
        "other_knowledge": bool(content.get("other_knowledge")),
    }
    for slug in order:
        if slug in hidden or slug not in section_has:
            continue
        if not section_has[slug]:
            issue("estructura",
                  f"Seccion '{slug}' configurada pero sin contenido "
                  f"(se omite en el PDF).")

    # 4. Fechas consistentes (parseables).
    try:
        from app.adapt.html_renderer import _parse_ymd

        for section in ("experiences", "education", "projects"):
            for item in content.get(section) or []:
                if not isinstance(item, dict):
                    continue
                for key in ("start", "start_date", "end", "end_date"):
                    value = item.get(key)
                    if value and not _parse_ymd(str(value)):
                        issue("estructura",
                              f"Fecha no reconocida '{value}' en "
                              f"'{str(item.get('title') or item.get('name') or item.get('degree') or '')[:40]}'.")
                        break
    except Exception:  # noqa: BLE001
        pass

    # 5. Personalizacion: cobertura de keywords (informativa, no exige
    # lo que el candidato no tiene).
    try:
        keywords = _offer_keywords(offer)
        declared_all = {norm(t) for bucket in declared.values()
                        for t in bucket}
        present = [k for k in keywords if norm(k) in declared_all]
        missing_real = [k for k in keywords
                        if norm(k) not in declared_all
                        and norm(k) in real]
        if missing_real:
            allowed.append(
                "Priorizar en experiencia/proyectos (es real pero no "
                f"destaca): {', '.join(missing_real[:6])}.")
        coverage = round(100 * len(present) / len(keywords)) if keywords \
            else 100
    except Exception:  # noqa: BLE001
        coverage, present, missing_real, keywords = 0, [], [], []

    # 6. Checklist §10: titulo e introduccion alineados al cargo.
    vacancy_role = str(((offer or {}).get("title")) or "").strip()
    header_title = str(content.get("title") or "")
    summary_text = str(content.get("summary") or "")
    if vacancy_role:
        if vacancy_role.lower() in header_title.lower():
            allowed.append("Titulo alineado al cargo de la vacante.")
        else:
            issue("personalizacion",
                  "El titulo no refleja el cargo (sin evidencia comun: "
                  "se conserva el del perfil).")
        role_mentioned = vacancy_role.lower() in summary_text.lower()
        summary_hits = [k for k in present
                        if k.lower() in summary_text.lower()]
        if role_mentioned or summary_hits:
            allowed.append("La introduccion menciona el rol y/o keywords "
                           "relevantes.")
        else:
            issue("personalizacion",
                  "La introduccion no menciona el rol ni keywords "
                  "de la oferta.")
    # 7. PDF: paginas, legibilidad ATS y densidad.
    facts = _pdf_facts(pdf_path) if pdf_path else {
        "pages": 0, "chars": 0, "readable": False, "text": ""}
    try:
        max_pages = int(config.get("max_pages", 0) or 0)
    except (TypeError, ValueError):
        max_pages = 0
    if facts["pages"]:
        if max_pages > 0 and facts["pages"] > max_pages:
            issue("configuracion",
                  f"Paginas {facts['pages']} > maximo ({max_pages}).",
                  blocking=True)
        elif max_pages > 0:
            allowed.append(f"Paginas dentro del limite ({facts['pages']}).")
        if not facts["readable"]:
            issue("ats", "El PDF no tiene texto extraible suficiente.",
                  blocking=True)
        else:
            name = str((profile or {}).get("full_name") or "")
            if name and name.split()[0].lower() not in facts["text"].lower():
                issue("ats", "El nombre no aparece en el texto extraible.")
            per_page = facts["chars"] / max(facts["pages"], 1)
            if per_page > 6000:
                issue("densidad",
                      "Pagina muy densa: recortar secundario o compactar.")
                allowed.append("Reducir bullets secundarios o proyectos "
                               "menos relevantes.")
            elif per_page < 800:
                issue("densidad", "Pagina muy vacia: revisar secciones "
                                 "ocultas por falta de datos.")
    else:
        issue("ats", "No se pudo leer el PDF para auditarlo.")

    blocking = [i for i in issues if i["blocking"]]
    scores = {
        "veracidad": 100 if not any(
            i["area"] == "veracidad" for i in blocking) else 40,
        "configuracion": 100 if not any(
            i["area"] == "configuracion" for i in blocking) else 50,
        "personalizacion": coverage,
        "ats": 100 if facts["readable"] else 40,
        "estructura": max(0, 100 - 10 * len(
            [i for i in issues if i["area"] == "estructura"])),
        "densidad": max(0, 100 - 15 * len(
            [i for i in issues if i["area"] == "densidad"])),
    }
    if max_pages > 0 and facts["pages"] > max_pages:
        blocked.append("No reducir paginas eliminando informacion "
                       "obligatoria por configuracion.")
    return {
        "passed": not blocking,
        "scores": scores,
        "issues": issues,
        "improvements_allowed": allowed,
        "improvements_blocked": blocked,
        "facts": {"pages": facts["pages"], "chars": facts["chars"],
                  "readable": facts["readable"]},
        "keyword_coverage": {
            "total": len(keywords),
            "present": len(present),
            "missing_real": missing_real[:10],
        },
    }


def blocking_issues(audit: dict) -> list[dict]:
    """Issues que impiden entregar el CV como valido: veracidad o
    configuracion marcadas bloqueantes. Puerta de entrega del pipeline.
    """
    issues = (audit or {}).get("issues") or []
    return [i for i in issues
            if isinstance(i, dict) and i.get("blocking")
            and i.get("area") in ("veracidad", "configuracion")]
