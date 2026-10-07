"""Seleccion del contenido del CV (FASE 4).

Recibe perfil + oferta + matching y produce el objeto compacto del CV:
lo relevante primero, con topes para que quepa en una hoja.
"""
from __future__ import annotations

from app.adapt.defaults import LIMIT_DEFAULTS

# Alias historicos (misma fuente unica ahora).
MAX_EXPERIENCE = LIMIT_DEFAULTS["max_experiences"]
MAX_PROJECTS = LIMIT_DEFAULTS["max_projects"]
MAX_CERTIFICATIONS = LIMIT_DEFAULTS["max_certifications"]
MAX_EDUCATION = LIMIT_DEFAULTS["max_education"]
MAX_SKILLS = LIMIT_DEFAULTS["max_skills"]


def _limit(config: dict | None, key: str, default: int) -> int:
    """Limite desde pdf_config. 0/faltante = default historico."""
    if not config:
        return default
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _top(ranked: list[dict], limit: int) -> list[dict]:
    return [row["item"] for row in (ranked or [])[:limit]]


def _keywords_set(matching: dict) -> set[str]:
    from app.analysis.signals import norm

    words: set[str] = set()
    for key in ("matched_skills",):
        for skill in matching.get(key) or []:
            words.update(t for t in norm(str(skill)).split(" ") if len(t) > 1)
    vacancy = matching.get("vacancy") or {}
    for key in ("keywords_high", "keywords_medium", "title_keywords"):
        for term in vacancy.get(key) or []:
            words.update(t for t in norm(str(term)).split(" ") if len(t) > 1)
    return words


def _score_text(text: str, keywords: set[str]) -> int:
    from app.analysis.signals import norm

    tokens = {t for t in norm(text).split(" ") if len(t) > 1}
    return len(tokens & keywords)


def compose_title(profile_title: str, vacancy: dict,
                  matched: list) -> str:
    """'{perfil} | {rol}' solo con evidencia real en comun.

    Sin rol, sin evidencia (sin skills en comun) o rol ya contenido:
    se conserva el titulo del perfil. Nunca inventa cargos.
    """
    base = str(profile_title or "").strip()
    role = str((vacancy or {}).get("role") or "").strip()
    if not role or not base or not matched:
        return base or role
    if role.lower() in base.lower() or base.lower() in role.lower():
        return base
    composed = f"{base} | {role}"
    return composed if len(composed) <= 90 else base


def order_summary(summary: str, keywords: set[str]) -> str:
    """Reordena oraciones por relevancia (estable, sin recortar ni
    reescribir)."""
    from app.adapt.html_renderer import _split_sentences

    sentences = _split_sentences(summary)
    scored = sorted(enumerate(sentences),
                    key=lambda p: (-_score_text(p[1], keywords), p[0]))
    return " ".join(s for _, s in scored)


def order_bullets(description: str, keywords: set[str]) -> list[str]:
    """Oraciones menos la primera, ordenadas por relevancia."""
    from app.adapt.html_renderer import _split_sentences

    sentences = _split_sentences(description)
    rest = sentences[1:] if len(sentences) > 1 else []
    return [s for _, s in sorted(
        enumerate(rest), key=lambda p: (-_score_text(p[1], keywords), p[0]))]


def _truncate_secondary(text: str, limit: int = 220) -> str:
    """Recorta proyectos secundarios por oracion (subconjunto)."""
    from app.adapt.html_renderer import _split_sentences

    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    kept: list[str] = []
    for sentence in _split_sentences(text):
        if kept and len(" ".join(kept)) + len(sentence) > limit:
            break
        kept.append(sentence)
    return " ".join(kept).strip() or text[:limit].strip()


def select_cv_content(
    profile: dict, offer: dict, matching: dict,
    config: dict | None = None,
) -> dict:
    """Arma el JSON personalizado del CV (forma FASE 4).

    `config` (pdf_config coercionada) manda sobre los topes: si el
    usuario fijo maximo 2 proyectos, salen 2 aunque haya 3 buenos.
    Sin config, topes historicos.
    """
    matched = list(matching.get("matched_skills") or [])
    vacancy = matching.get("vacancy") or {}
    keywords = _keywords_set(matching)
    # Skills: primero las exigidas por la oferta (en su orden), luego
    # el resto en orden del perfil. Solo reales (matched ya lo es).
    required_order = list(vacancy.get("requirements") or [])
    from app.analysis.signals import norm as _norm

    def _req_rank(skill: str) -> tuple[int, int]:
        key = _norm(skill)
        for i, req in enumerate(required_order):
            if _norm(str(req)) == key:
                return (0, i)
        return (1, 0)

    ordered_matched = sorted(
        enumerate(matched),
        key=lambda p: (_req_rank(p[1]), p[0]))
    skills: list[str] = []
    seen: set[str] = set()

    def add(skill: str | None) -> None:
        text = str(skill or "").strip()
        lowered = text.lower()
        if text and lowered not in seen and len(skills) < MAX_SKILLS:
            skills.append(text)
            seen.add(lowered)

    for _, skill in ordered_matched:
        add(skill)
    for skill in profile.get("skills_technical") or []:
        add(skill)
    for skill in profile.get("skills_soft") or []:
        add(skill)

    experiences = _top(matching.get("experiences"),
                       _limit(config, "max_experiences", MAX_EXPERIENCE))
    projects = _top(matching.get("projects"),
                    _limit(config, "max_projects", MAX_PROJECTS))
    certifications = _top(matching.get("certifications"), MAX_CERTIFICATIONS)
    education = _top(matching.get("education"), MAX_EDUCATION)

    # Bullets reordenados por relevancia (mismos hechos, otro orden).
    # Solo cuando la entrada no trae bullets propios del autor.
    scored_experiences = []
    for exp in experiences:
        exp = dict(exp) if isinstance(exp, dict) else exp
        if isinstance(exp, dict) and not exp.get("bullets") \
                and not exp.get("achievements") \
                and exp.get("description"):
            ordered = order_bullets(str(exp["description"]), keywords)
            if ordered:
                exp["bullets"] = ordered
        scored_experiences.append(exp)
    experiences = scored_experiences

    # Proyectos secundarios con detalle reducido (subconjunto).
    trimmed_projects = []
    for i, proj in enumerate(projects):
        proj = dict(proj) if isinstance(proj, dict) else proj
        if isinstance(proj, dict) and i > 0 and proj.get("description"):
            proj["description"] = _truncate_secondary(
                str(proj["description"]))
        trimmed_projects.append(proj)
    projects = trimmed_projects

    profile_title = str(profile.get("title") or "").strip()
    target_role = str(offer.get("title") or "").strip()
    for role in profile.get("target_roles") or []:
        if role and role.lower() in str(offer.get("title") or "").lower():
            target_role = role
            break
    if not target_role:
        target_role = profile_title

    return {
        "target_role": target_role,
        # Titulo compuesto para el encabezado (solo con evidencia).
        "title_line": compose_title(profile_title, vacancy, matched),
        "company": str(offer.get("company") or "").strip(),
        "summary": order_summary(
            str(profile.get("summary") or "").strip(), keywords),
        "skills": skills,
        "skills_groups": profile.get("skills_groups") or {},
        "skills_soft": profile.get("skills_soft") or [],
        "other_studies": profile.get("other_studies") or [],
        "other_knowledge": profile.get("other_knowledge") or [],
        "experiences": experiences,
        "education": education,
        "projects": projects,
        "certifications": certifications,
        "languages": list(profile.get("languages") or []),
        "matching": {
            "percentage": matching.get("percentage", 0),
            "matched_skills": matched,
            "missing_skills": list(matching.get("missing_skills") or []),
        },
    }
