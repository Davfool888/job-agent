"""Matching deterministico oferta <-> perfil (FASE 3).

Sin LLM, sin red: reutiliza la taxonomia de `analysis.signals`
(normalizacion + limites de palabra) con vocabulario propio ampliado
para desarrollo. Reglas simples y modificables en un solo lugar.
"""
from __future__ import annotations


EXTRA_SKILLS: list[str] = [
    "JavaScript", "TypeScript", "React", "Angular", "Vue", "Node.js",
    "VS Code", "JSON", "Postman", "Scrum", "Figma", ".NET", "C#",
    "Java", "Spring", "MySQL",
]


def _vocab() -> list[tuple[str, list[str]]]:
    """[(etiqueta, [variantes])] desde signals + extras de desarrollo."""
    from app.analysis import signals as sig

    vocab: list[tuple[str, list[str]]] = [
        (label, [label, *aliases]) for label, aliases, _tier in sig.SKILLS
    ]
    seen = {label.lower() for label, _ in vocab}
    for tool in sig.TOOLS:
        if tool.lower() not in seen:
            vocab.append((tool, [tool]))
            seen.add(tool.lower())
    for extra in EXTRA_SKILLS:
        if extra.lower() not in seen:
            vocab.append((extra, [extra]))
    return vocab


def offer_text(offer: dict) -> str:
    parts = [
        offer.get("title"), offer.get("company"), offer.get("description"),
        offer.get("location"), offer.get("modality"),
    ]
    for key in ("requirements", "responsibilities", "skills", "tags",
                "technologies", "keywords"):
        value = offer.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    return " ".join(p for p in parts if p)


def profile_skills(profile: dict) -> list[str]:
    """Skills unicas en orden: tecnicas, blandas, grupos y tecnicas
    usadas en experiencia/proyectos/certificaciones (demostrables)."""
    from app.analysis.signals import norm

    seen: list[str] = []
    seen_norm: set[str] = set()
    groups = profile.get("skills_groups") or {}
    ordered = list(profile.get("skills_technical") or []) + list(
        profile.get("skills_soft") or [])
    if isinstance(groups, dict):
        for group in groups.values():
            ordered.extend(group or [])
    for section in ("experience", "projects", "certifications"):
        for item in profile.get(section) or []:
            if isinstance(item, dict):
                ordered.extend(item.get("technical_skills") or [])
    for skill in ordered:
        text = str(skill or "").strip()
        key = norm(text)
        if text and key not in seen_norm:
            seen.append(text)
            seen_norm.add(key)
    return seen


def match_offer_profile(offer: dict, profile: dict) -> dict:
    """Compara oferta y perfil. Todo local y deterministico."""
    from app.analysis.signals import norm, phrases_found

    text_norm = norm(offer_text(offer))
    keywords = {t for t in text_norm.split(" ") if len(t) > 1}
    try:
        from app.adapt.vacancy import analyze_vacancy

        vacancy = analyze_vacancy(offer)
        title_keywords = {norm(t) for t in vacancy["title_keywords"]}
    except Exception:  # noqa: BLE001
        vacancy = {"role": str(offer.get("title") or ""),
                   "requirements": [], "keywords_high": [],
                   "keywords_medium": [], "keywords_low": [],
                   "keywords_all": [], "title_keywords": [],
                   "sector": None, "seniority": None}
        title_keywords = set()
    skills = profile_skills(profile)

    matched: list[str] = []
    for skill in skills:
        variants = [skill]
        for label, aliases in _vocab():
            if norm(label) == norm(skill):
                variants = [label, *aliases]
                break
        if phrases_found(text_norm, variants):
            matched.append(skill)

    required = offer_required_skills(offer, text_norm)
    matched_norm = {norm(s) for s in matched}
    missing = [s for s in required if norm(s) not in matched_norm]

    # Porcentaje: si la oferta declara skills (estructurados), manda la
    # cobertura sobre ellos (ej: 4/4 = 100). Si no, ratio vocabulario.
    explicit = explicit_required_skills(offer)
    explicit_norm = {norm(s) for s in explicit}
    matched_exp = [s for s in matched if norm(s) in explicit_norm]
    if explicit:
        percentage = round(100 * len(matched_exp) / len(explicit))
    else:
        total = len(matched) + len(missing)
        percentage = round(100 * len(matched) / total) if total else 0

    experiences = _ranked((profile.get("experience") or profile.get("experiences") or []), keywords, title_keywords)
    projects = _ranked(profile.get("projects") or [], keywords, title_keywords)
    certifications = _ranked(profile.get("certifications") or [], keywords, title_keywords)
    education = _ranked(profile.get("education") or [], keywords, title_keywords)

    modality_offer = norm(offer.get("modality"))
    modality_profile = norm(profile.get("modality"))
    modality_ok = (not modality_offer or not modality_profile
                   or modality_offer == modality_profile)

    location_ok = (not norm(offer.get("location"))
                   or not norm(profile.get("location"))
                   or norm(profile.get("location")) in text_norm
                   or norm(offer.get("location")) in norm(
                       profile.get("location")))

    target_hits = [role for role in profile.get("target_roles") or []
                   if norm(role) and norm(role) in text_norm]

    years = profile.get("years_experience")
    try:
        years_value = float(years) if years not in (None, "") else None
    except (TypeError, ValueError):
        years_value = None

    return {
        "percentage": percentage,
        "matched_skills": matched,
        "missing_skills": missing,
        "vacancy": vacancy,
        "experiences": experiences,
        "projects": projects,
        "certifications": certifications,
        "education": education,
        "other_studies": profile.get("other_studies") or [],
        "other_knowledge": profile.get("other_knowledge") or [],
        "modality_ok": modality_ok,
        "location_ok": location_ok,
        "target_roles_matched": target_hits,
        "years_experience": years_value,
    }


def explicit_required_skills(offer: dict) -> list[str]:
    """Skills declaradas en campos estructurados (skills, technologies,
    tags, requirements). Base del porcentaje cuando existen."""
    from app.analysis.signals import norm

    explicit: list[str] = []
    seen: set[str] = set()

    def add(text: str | None) -> None:
        text = str(text or "").strip(" -•\t")
        key = norm(text)
        if len(text) > 1 and len(text) < 60 and key not in seen:
            explicit.append(text)
            seen.add(key)

    for key in ("skills", "technologies", "tags"):
        value = offer.get(key)
        items = value if isinstance(value, list) else (
            [value] if value else [])
        for item in items:
            add(item)
    value = offer.get("requirements")
    chunks = value if isinstance(value, list) else str(
        value or "").split("\n")
    for chunk in chunks:
        for token in str(chunk).split(","):
            add(token)
    return explicit


def offer_required_skills(offer: dict, text_norm: str) -> list[str]:
    """Skills que pide la oferta: estructurados + vocabulario conocido
    mencionado en el texto (transparencia en missing_skills)."""
    from app.analysis.signals import norm, phrases_found

    required = explicit_required_skills(offer)
    seen = {norm(s) for s in required}
    for label, aliases in _vocab():
        if phrases_found(text_norm, [label, *aliases]) and norm(
                label) not in seen:
            required.append(label)
            seen.add(norm(label))
    return required


def _item_text(item: dict) -> str:
    parts = [item.get("title"), item.get("name"), item.get("degree"),
             item.get("company"), item.get("institution"),
             item.get("description")]
    for key in ("technical_skills", "soft_skills", "technologies"):
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
    for perspective in item.get("perspectives") or []:
        if isinstance(perspective, dict):
            parts.append(perspective.get("label"))
            parts.extend(perspective.get("skills") or [])
            parts.extend(perspective.get("tools") or [])
    return " ".join(str(p) for p in parts if p)


def _ranked(items: list[dict], keywords: set[str],
            title_keywords: set[str] | None = None) -> list[dict]:
    """Ordena por coincidencia ponderada: titulo x3, resto x1.

    Estable: a igual puntaje conserva el orden del perfil. Solo
    reordena, jamas filtra ni reescribe. Devuelve COPIAS superficiales:
    mutar el resultado nunca toca el perfil display de entrada.
    """
    from app.analysis.signals import norm

    title_keywords = title_keywords or set()
    scored = []
    for i, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        tokens = {t for t in norm(_item_text(item)).split(" ") if len(t) > 1}
        base = len(tokens & keywords)
        title_hits = len(tokens & title_keywords)
        scored.append((base + 2 * title_hits, i, dict(item)))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [{"score": score, "item": item} for score, _, item in scored]
