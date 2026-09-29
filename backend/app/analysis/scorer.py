"""Scoring deterministico oferta-vs-perfil (sin llamadas IA).

Estructura (pesos ajustables):
  titulo            0-20
  habilidades       0-30
  responsabilidades 0-30
  herramientas      0-20
  TOTAL             0-100

Una oferta puede puntuar alto aunque el titulo no sea de datos,
siempre que el CONTENIDO traiga señales. Una sola evidencia debil
(ej: "Excel" suelto) nunca clasifica un rol (ver signals.py).
"""
from __future__ import annotations

import re

from app.analysis import signals
from app.analysis.signals import norm
from app.analysis.signals import phrases_found

TIER_SKILL_POINTS = {"strong": 6, "medium": 3, "weak": 1}
TIER_RESP_POINTS = {"strong": 6, "medium": 3, "weak": 1}
TOOL_POINTS = 5

EXPERIENCE_RE = re.compile(
    r"(\d+)\s*(?:\+)?\s*años?\s+de\s+experiencia", re.IGNORECASE
)
NO_EXPERIENCE_RE = re.compile(
    r"sin\s+experiencia|no\s+(?:requiere|se\s+requiere)\s+experiencia",
    re.IGNORECASE,
)


def _content_of(job: dict) -> tuple[str, str, str]:
    title = norm(job.get("title"))
    description = norm(job.get("description"))
    extra = norm(
        " ".join(
            str(job.get(key) or "")
            for key in ("requirements", "skills", "tags")
            if job.get(key)
        )
    )
    return title, description, extra


def _title_score(title: str, content: str) -> tuple[int, list[str]]:
    if not title:
        return 0, []
    for _role, keys in signals.ROLES.items():
        if phrases_found(title, keys["titles"]):
            return 20, [f"titulo: {keys['titles'][0]}"]
    hits = phrases_found(
        title,
        [label for label, _a, tier in signals.SKILLS if tier == "strong"],
    )
    if hits:
        return 12, [f"titulo menciona: {h}" for h in hits[:2]]
    med = phrases_found(
        title,
        [label for label, _a, tier in signals.SKILLS if tier == "medium"],
    )
    if med:
        return 6, [f"titulo menciona: {med[0]}"]
    if phrases_found(title, ["datos", "data", "bi", "informacion", "reportes"]):
        return 4, ["titulo con termino afin"]
    _ = content
    return 0, []


def _skills_score(content: str) -> tuple[int, list[str], list[str]]:
    """(puntos, evidencias strong+medium, todas las habilidades)."""
    total = 0
    evidence: list[str] = []
    matched: list[str] = []
    for label, aliases, tier in signals.SKILLS:
        found = phrases_found(content, aliases)
        if not found:
            continue
        matched.append(label)
        total += TIER_SKILL_POINTS[tier]
        if tier in ("strong", "medium"):
            evidence.append(label)
    return min(total, 30), evidence, matched


def _resp_score(content: str) -> tuple[int, list[str]]:
    total = 0
    evidence: list[str] = []
    for label, variants, tier in signals.RESPONSIBILITIES:
        if phrases_found(content, variants):
            total += TIER_RESP_POINTS[tier]
            if tier in ("strong", "medium"):
                evidence.append(label)
    return min(total, 30), evidence


def _tools_score(content: str) -> tuple[int, list[str]]:
    hits = phrases_found(content, signals.TOOLS)
    return min(len(hits) * TOOL_POINTS, 20), hits[:6]


def _detect_role(
    title: str, content: str
) -> tuple[str, int, list[str]]:
    """Devuelve (rol, puntos, evidencias_del_rol).

    Regla anti-falsos-positivos (§12): clasificar exige
    >= ROLE_MIN_POINTS puntos de evidencia del rol Y
    (>=1 strong O titulo-del-rol + >=1 medium).
    """
    best_role = "OTHER"
    best_points = 0
    best_evidence: list[str] = []

    for role, keys in signals.ROLES.items():
        title_hit = bool(phrases_found(title, keys["titles"]))
        strong_hits = phrases_found(content, keys["strong"])
        medium_hits = phrases_found(content, keys["medium"])
        points = (4 if title_hit else 0) + 3 * len(strong_hits) + len(
            medium_hits
        )
        qualifies = points >= signals.ROLE_MIN_POINTS and (
            strong_hits or (title_hit and medium_hits)
        )
        if qualifies and points > best_points:
            best_role = role
            best_points = points
            best_evidence = (
                [f"titulo: {keys['titles'][0]}"] if title_hit else []
            ) + strong_hits + medium_hits[:3]

    return best_role, best_points, best_evidence


def _profile_match(  # noqa: F401 (referencia historica; ver matching_service)
    content: str, profile: dict
) -> tuple[list[str], list[str]]:
    from app.services import matching_service

    fit = matching_service.profile_fit(content, profile)
    return fit["matched_skills"], fit["missing_skills"]


def _experience_required(job: dict, content_norm: str) -> str | None:
    raw = " ".join(
        str(job.get(key) or "")
        for key in ("description", "requirements")
    )
    match = EXPERIENCE_RE.search(raw)
    if match:
        years = match.group(1)
        return f"{years} año(s) de experiencia"
    if NO_EXPERIENCE_RE.search(raw):
        return "sin experiencia"
    _ = content_norm
    return None


def analyze_job(job: dict, profile: dict | None = None) -> dict:
    """Analiza titulo+descripcion+requisitos y devuelve el dict que
    persiste el backend. El score final sale de matching_service
    (pesos configurables + bonus de rol objetivo)."""
    from app.services import matching_service

    profile = profile or {}
    title, description, extra = _content_of(job)
    content = f"{title} {description} {extra}".strip()

    title_pts, title_ev = _title_score(title, content)
    skills_pts, skills_ev, _skills_all = _skills_score(content)
    resp_pts, resp_ev = _resp_score(content)
    tools_pts, _tools = _tools_score(content)

    breakdown = {
        "title": title_pts,
        "skills": skills_pts,
        "responsibilities": resp_pts,
        "tools": tools_pts,
    }

    role, _role_pts, role_ev = _detect_role(title, content)

    matched_result = matching_service.combine(
        breakdown, role, profile, content
    )

    # Evidencia ordenada y sin duplicados (insensible a mayusculas):
    # titulo > rol strong > skills > responsabilidades.
    evidence: list[str] = []
    seen_evidence: set[str] = set()
    for item in title_ev + role_ev + skills_ev + resp_ev:
        key = item.lower()
        if key not in seen_evidence:
            seen_evidence.add(key)
            evidence.append(item)
    evidence = evidence[:8]

    return {
        "match_score": matched_result["match_score"],
        "detected_role": role.replace("_", " ").title()
        if role != "OTHER"
        else None,
        "category": role,
        "evidence": evidence,
        "matched_skills": matched_result["matched_skills"],
        "missing_skills": matched_result["missing_skills"],
        "experience_required": _experience_required(job, content),
        "role_matches_goal": matched_result["role_matches_goal"],
        "score_breakdown": breakdown,
        "content_score": matched_result["content_score"],
        "goal_bonus": matched_result["goal_bonus"],
    }
