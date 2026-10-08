"""Matching oferta-vs-perfil (§6): pesos configurables en config.py.

Separa el score de CONTENIDO (titulo/skills/responsabilidades/tools,
pesos MATCH_WEIGHTS) del ajuste de PERFIL (rol objetivo + habilidades).
No hardcodea: los pesos viven en .env (MATCH_W_*).
"""
from __future__ import annotations

from app.analysis.signals import norm
from app.analysis.signals import phrases_found
from app.config import MATCH_WEIGHTS

# Maximo de cada componente (caps del scorer).
COMPONENT_MAX = {
    "title": 20.0,
    "skills": 30.0,
    "responsibilities": 30.0,
    "tools": 20.0,
}

# Bonus deterministico y documentado por alineacion con el rol objetivo.
GOAL_BONUS = 5.0


def profile_fit(content_norm: str, profile: dict) -> dict:
    from app.analysis.skills_canonical import _IMPLIES
    from app.analysis.skills_canonical import canonical_key
    from app.analysis.skills_canonical import normalize_skill_list

    raw_skills = [
        str(s) for s in (profile.get("skills") or []) if str(s).strip()
    ]
    # Perfil a canonicas (PowerBi/power bi -> Power BI; Tools -> None).
    canon_profile = normalize_skill_list(raw_skills, limit=30)
    matched, missing = [], []
    for skill in canon_profile:
        key = canonical_key(skill)
        variants = {key, key.replace(" ", "")}
        # Alias de la canonica: si el perfil dice PostgreSQL y la oferta
        # pide SQL, tambien cuenta (dialecto implica base, no al reves).
        for implied in _IMPLIES.get(skill, ()):
            implied_key = canonical_key(implied)
            variants.add(implied_key)
            variants.add(implied_key.replace(" ", ""))
        if any(phrases_found(content_norm, [v]) for v in variants if v):
            matched.append(skill)
        else:
            missing.append(skill)
    # Oferta dialecto vs perfil base: si el perfil dice SQL y la oferta
    # trae postgresql/mysql, cuenta como match.
    if missing:
        still_missing = []
        for skill in missing:
            key = canonical_key(skill)
            dialect_hit = any(
                phrases_found(content_norm, [canonical_key(d)])
                for canon, bases in _IMPLIES.items()
                if key in {canonical_key(b) for b in bases}
                for d in (canon, canon.replace(" ", ""))
            )
            (matched if dialect_hit else still_missing).append(skill)
        missing = still_missing

    targets = [norm(str(t)) for t in (profile.get("target_roles") or [])]
    role_matches_goal = False
    return {
        "matched_skills": matched,
        "missing_skills": missing[:10],
        "targets": [t for t in targets if t],
        "role_matches_goal": role_matches_goal,
    }


def role_goal_bonus(category: str, targets: list[str]) -> float:
    """+GOAL_BONUS si la categoria matchea un rol objetivo."""
    if not category or category == "OTHER" or not targets:
        return 0.0
    cat = norm(category)
    for target in targets:
        if target and (target in cat or cat in target):
            return GOAL_BONUS
    return 0.0


def combine(
    breakdown: dict[str, float],
    category: str,
    profile: dict,
    content_norm: str,
    job: dict | None = None,
    analysis: dict | None = None,
) -> dict:
    """Reescala componentes por pesos configurables (0-100), suma el
    bonus de rol objetivo y el bonus de perspectivas (acotado): si alguna
    perspectiva del perfil es muy relevante para la vacante, suma hasta
    +8. Adjunta top_perspectives para trazabilidad."""
    weights = MATCH_WEIGHTS
    total_weight = sum(weights.values()) or 100
    weighted = 0.0
    for key, maximum in COMPONENT_MAX.items():
        value = min(maximum, breakdown.get(key, 0))
        weighted += (value / maximum) * weights.get(key, 0)
    content_total = round(weighted * 100 / total_weight, 1)

    fit = profile_fit(content_norm, profile)
    bonus = role_goal_bonus(category, fit["targets"])
    fit["role_matches_goal"] = bonus > 0

    perspective_bonus = 0.0
    top_perspectives: list[dict] = []
    if job is not None:
        try:
            from app.profile.perspectives import (
                MAX_PERSPECTIVE_BONUS,
                select_perspectives,
            )

            selection = select_perspectives(
                profile, job, analysis or {}, max_total=3, min_score=0.0
            )
            for block in selection["selection"]:
                top_perspectives.append({
                    "section": block["section"],
                    "item": block["item_title"],
                    "perspective": block["perspective"],
                    "relevance_score": block["relevance_score"],
                })
            if top_perspectives:
                best = max(b["relevance_score"] for b in top_perspectives)
                perspective_bonus = round(
                    min(MAX_PERSPECTIVE_BONUS, best * 0.08), 1
                )
        except Exception:
            perspective_bonus = 0.0
            top_perspectives = []

    final = min(100.0, round(content_total + bonus + perspective_bonus, 1))
    return {
        "match_score": final,
        "content_score": round(content_total, 1),
        "goal_bonus": bonus,
        "perspective_bonus": perspective_bonus,
        "top_perspectives": top_perspectives,
        "weights": dict(weights),
        **fit,
    }
