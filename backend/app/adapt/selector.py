"""Seleccion del contenido del CV (FASE 4).

Recibe perfil + oferta + matching y produce el objeto compacto del CV:
lo relevante primero, con topes para que quepa en una hoja.
"""
from __future__ import annotations

MAX_EXPERIENCE = 3
MAX_PROJECTS = 3
MAX_CERTIFICATIONS = 3
MAX_EDUCATION = 2
MAX_SKILLS = 12


def _top(ranked: list[dict], limit: int) -> list[dict]:
    return [row["item"] for row in (ranked or [])[:limit]]


def select_cv_content(
    profile: dict, offer: dict, matching: dict
) -> dict:
    """Arma el JSON personalizado del CV (forma FASE 4)."""
    matched = list(matching.get("matched_skills") or [])
    skills: list[str] = []
    seen: set[str] = set()

    def add(skill: str | None) -> None:
        text = str(skill or "").strip()
        lowered = text.lower()
        if text and lowered not in seen and len(skills) < MAX_SKILLS:
            skills.append(text)
            seen.add(lowered)

    for skill in matched:
        add(skill)
    for skill in profile.get("skills_technical") or []:
        add(skill)
    for skill in profile.get("skills_soft") or []:
        add(skill)

    experiences = _top(matching.get("experiences"), MAX_EXPERIENCE)
    projects = _top(matching.get("projects"), MAX_PROJECTS)
    certifications = _top(matching.get("certifications"), MAX_CERTIFICATIONS)
    education = _top(matching.get("education"), MAX_EDUCATION)

    target_role = str(offer.get("title") or "").strip()
    for role in profile.get("target_roles") or []:
        if role and role.lower() in str(offer.get("title") or "").lower():
            target_role = role
            break
    if not target_role:
        target_role = str(profile.get("title") or "").strip()

    return {
        "target_role": target_role,
        "company": str(offer.get("company") or "").strip(),
        "summary": str(profile.get("summary") or "").strip(),
        "skills": skills,
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
