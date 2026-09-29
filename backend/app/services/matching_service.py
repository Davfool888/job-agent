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
    skills = [
        str(s) for s in (profile.get("skills") or []) if str(s).strip()
    ]
    matched, missing = [], []
    for skill in skills[:30]:
        variants = [skill, norm(skill).replace(" ", "")]
        if any(phrases_found(content_norm, [v]) for v in variants):
            matched.append(skill)
        else:
            missing.append(skill)

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
) -> dict:
    """Reescala componentes por pesos configurables (0-100) y suma el
    bonus de rol objetivo."""
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
    final = min(100.0, round(content_total + bonus, 1))
    return {
        "match_score": final,
        "content_score": round(content_total, 1),
        "goal_bonus": bonus,
        "weights": dict(weights),
        **fit,
    }
