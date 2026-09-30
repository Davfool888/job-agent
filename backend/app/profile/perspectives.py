"""Perspectivas modulares del perfil (§1-§7).

Una experiencia/educacion/proyecto puede tener N perspectivas: cada una
describe que parte REAL de ese item es relevante para cierto tipo de
trabajo (descripcion + skills + tools + dominios + roles afines).

Regla de oro: solo se COPIA texto del perfil. Nada se inventa: la
seleccion filtra/ordena/reorganiza, y `validate_profile` avisa si una
perspectiva menciona skills no declarados en la base.
"""
from __future__ import annotations

import re

from app.analysis.domains import canonical_domain
from app.analysis.domains import detect_domains
from app.analysis.signals import norm
from app.analysis.signals import phrases_found

# Secciones del perfil que pueden tener items con perspectivas.
SECTIONS = ("experience", "education", "projects", "certifications")

PERSPECTIVE_KEYS = (
    "id", "label", "description", "skills", "tools", "domains", "roles",
)

# Pesos de relevancia (suman 100). Constantes documentadas, no magicas.
PERSPECTIVE_WEIGHTS = {
    "skills": 30.0,
    "tools": 20.0,
    "role": 20.0,
    "domain": 15.0,
    "industry": 10.0,
    "experience": 5.0,
}

# Bonus maximo que una perspectiva puede aportar al match_score global.
MAX_PERSPECTIVE_BONUS = 8.0


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalize_perspective(raw: dict, index: int = 0) -> dict:
    raw = raw or {}
    return {
        "id": str(raw.get("id") or f"p{index + 1}"),
        "label": str(raw.get("label") or f"Perspectiva {index + 1}").strip(),
        "description": str(raw.get("description") or "").strip(),
        "skills": _as_list(raw.get("skills")),
        "tools": _as_list(raw.get("tools")),
        "domains": [
            d for d in
            (canonical_domain(x) or norm(x) for x in _as_list(raw.get("domains")))
            if d
        ],
        "roles": _as_list(raw.get("roles")),
    }


def normalize_entry(entry: dict) -> dict:
    entry = dict(entry or {})
    entry["perspectives"] = [
        normalize_perspective(p, i)
        for i, p in enumerate(entry.get("perspectives") or [])
        if isinstance(p, dict)
    ]
    return entry


def flatten_profile_skills(profile: dict) -> list[str]:
    """Une skills planas + grupos + TODAS las perspectivas (orden, sin
    duplicados). Compatible con perfiles viejos sin perspectivas."""
    profile = profile or {}
    ordered: list[str] = []

    def add(values) -> None:
        for value in _as_list(values):
            key = norm(value)
            if key and key not in {norm(s) for s in ordered}:
                ordered.append(value)

    add(profile.get("skills") if isinstance(profile.get("skills"), list) else [])
    skills = profile.get("skills") or {}
    if isinstance(skills, dict):
        for group in skills.values():
            add(group)
    for section in SECTIONS:
        items = profile.get(section) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for perspective in normalize_entry(item)["perspectives"]:
                add(perspective["skills"])
                add(perspective["tools"])
    return ordered


def declared_base_skills(profile: dict) -> set[str]:
    """Skills declarados fuera de perspectivas (la base verificable)."""
    profile = profile or {}
    base: set[str] = set()
    flat = profile.get("skills")
    if isinstance(flat, list):
        base.update(norm(s) for s in _as_list(flat))
    if isinstance(flat, dict):
        for group in flat.values():
            base.update(norm(s) for s in _as_list(group))
    return {s for s in base if s}


def validate_profile(profile: dict) -> list[str]:
    """Avisos (no errores fatales): skills/tools de perspectivas que no
    estan declarados en la base del perfil."""
    warnings: list[str] = []
    base = declared_base_skills(profile or {})
    if not base:
        return warnings
    for section in SECTIONS:
        for item in (profile or {}).get(section) or []:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("name") or item.get("degree") or "?"
            for perspective in normalize_entry(item)["perspectives"]:
                for skill in perspective["skills"] + perspective["tools"]:
                    if norm(skill) not in base:
                        warnings.append(
                            f"{section}/{title}/{perspective['label']}: "
                            f"'{skill}' no esta en skills base"
                        )
    return warnings


def _years_in(text: str | None) -> float | None:
    match = re.search(r"(\d+)\s*(?:\+)?\s*años?\s+de\s+experiencia", text or "",
                      re.IGNORECASE)
    if match:
        return float(match.group(1))
    if re.search(r"sin\s+experiencia", text or "", re.IGNORECASE):
        return 0.0
    return None


def extract_job_signals(job: dict, analysis: dict | None = None) -> dict:
    """Señales de la vacante: skills, tools, dominios, rol, sector, años."""
    analysis = analysis or {}
    text = " ".join(
        str(job.get(key) or "")
        for key in ("title", "description", "requirements", "responsibilities")
    )
    evidence = " ".join(str(e) for e in (analysis.get("evidence") or []))
    full = f"{text} {evidence}"
    return {
        "skills": [s.lower() for s in (analysis.get("matched_skills") or [])]
        + [s.lower() for s in (analysis.get("evidence") or [])],
        "tools": [],
        "domains": detect_domains(full),
        "sector": norm(job.get("sector")),
        "category": analysis.get("category") or "OTHER",
        "role": norm(analysis.get("detected_role") or ""),
        "years": _years_in(text),
        "text_norm": norm(full),
    }


def _overlap_ratio(needles: list[str], haystack_norm: str) -> float:
    if not needles:
        return 0.0
    hits = sum(
        1 for n in needles
        if phrases_found(haystack_norm, [n])
    )
    return hits / len(needles)


def score_perspective(perspective: dict, signals: dict) -> dict:
    """Relevancia 0-100 de UNA perspectiva contra la vacante."""
    perspective = normalize_perspective(perspective)
    p_text = norm(
        f"{perspective['label']} {perspective['description']} "
        f"{' '.join(perspective['skills'])} "
        f"{' '.join(perspective['tools'])}"
    )
    job_text = signals.get("text_norm", "")

    skills_match = _overlap_ratio(perspective["skills"], job_text)
    tools_match = _overlap_ratio(perspective["tools"], job_text)

    role_match = 0.0
    category = norm(signals.get("category") or "")
    role = signals.get("role") or ""
    for wanted in perspective["roles"]:
        wanted_norm = norm(wanted)
        if not wanted_norm:
            continue
        if wanted_norm in category or category in wanted_norm:
            role_match = 1.0
            break
        if role and (wanted_norm in role or role in wanted_norm):
            role_match = max(role_match, 0.7)
        elif phrases_found(job_text, [wanted]):
            role_match = max(role_match, 0.5)

    p_domains = set(perspective["domains"])
    j_domains = set(signals.get("domains") or [])
    domain_match = (
        len(p_domains & j_domains) / len(p_domains) if p_domains else 0.0
    )
    sector = signals.get("sector") or ""
    industry_match = 0.0
    if sector and p_domains:
        industry_match = 1.0 if (
            sector in p_domains
            or any(d in sector or sector in d for d in p_domains)
        ) else 0.0

    experience_match = 0.5  # neutral si no hay dato exigible
    years_needed = signals.get("years")
    if years_needed is not None:
        text_years = re.findall(r"(\d+)\s*años?", p_text)
        if text_years and max(map(int, text_years)) >= years_needed:
            experience_match = 1.0
        elif years_needed == 0:
            experience_match = 1.0
        else:
            experience_match = 0.2

    weights = PERSPECTIVE_WEIGHTS
    total = (
        skills_match * weights["skills"]
        + tools_match * weights["tools"]
        + role_match * weights["role"]
        + domain_match * weights["domain"]
        + industry_match * weights["industry"]
        + experience_match * weights["experience"]
    )
    matched_skills = [
        s for s in perspective["skills"]
        if phrases_found(job_text, [s])
    ]
    matched_domain = sorted(p_domains & j_domains)
    return {
        "perspective": perspective["label"],
        "perspective_id": perspective["id"],
        "relevance_score": round(total, 1),
        "matched_skills": matched_skills,
        "matched_domain": matched_domain,
        "breakdown": {
            "role_match": round(role_match * 100, 1),
            "skills_match": round(skills_match * 100, 1),
            "industry_match": round(industry_match * 100, 1),
            "domain_match": round(domain_match * 100, 1),
            "experience_match": round(experience_match * 100, 1),
            "tools_match": round(tools_match * 100, 1),
        },
    }


def _item_base_text(item: dict) -> str:
    parts = []
    for key in ("title", "name", "degree", "company", "institution",
                "period", "description", "summary"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    for key in ("bullets", "achievements", "technologies", "stack"):
        parts.extend(str(v) for v in _as_list(item.get(key)))
    return " ".join(parts)


def select_perspectives(
    profile: dict,
    job: dict,
    analysis: dict | None = None,
    max_total: int = 6,
    min_score: float = 20.0,
) -> dict:
    """Selecciona perspectivas relevantes (solo copia del perfil).

    Devuelve bloques adaptados con procedencia (seccion/item/perspectiva)
    para trazabilidad en el CV.
    """
    profile = profile or {}
    signals = extract_job_signals(job, analysis or {})
    ranked: list[dict] = []

    for section in SECTIONS:
        items = profile.get(section) or []
        if not isinstance(items, list):
            continue
        for position, raw in enumerate(items):
            if not isinstance(raw, dict):
                continue
            item = normalize_entry(raw)
            perspectives = item["perspectives"]
            if not perspectives:
                # Item sin perspectivas: bloque base si aporta algo.
                base_text = _item_base_text(item)
                if not base_text.strip():
                    continue
                generic = {
                    "id": "base", "label": "General",
                    "description": base_text[:600],
                    "skills": [], "tools": [],
                    "domains": detect_domains(base_text),
                    "roles": [],
                }
                scored = score_perspective(generic, signals)
            else:
                scored = None
                for perspective in perspectives:
                    candidate = score_perspective(perspective, signals)
                    if scored is None or candidate["relevance_score"] > scored[
                        "relevance_score"
                    ]:
                        scored = candidate
                        scored["perspective_data"] = perspective
            scored["section"] = section
            scored["item_index"] = position
            scored["item_title"] = (
                item.get("title") or item.get("name")
                or item.get("degree") or ""
            )
            scored["item_org"] = (
                item.get("company") or item.get("institution") or ""
            )
            ranked.append(scored)

    ranked.sort(key=lambda r: -r["relevance_score"])
    selected = [r for r in ranked if r["relevance_score"] >= min_score][
        :max_total
    ]
    combined_skills: list[str] = []
    for block in selected:
        for skill in block["matched_skills"]:
            if skill not in combined_skills:
                combined_skills.append(skill)
    return {
        "selection": selected,
        "combined_skills": combined_skills,
        "signals": {
            "domains": signals["domains"],
            "category": signals["category"],
            "role": signals.get("role"),
        },
    }


def build_tailored_profile(
    profile: dict, selection: dict, job: dict, analysis: dict | None = None
) -> dict:
    """Perfil adaptado: base bloqueada + bloques seleccionados con
    procedencia. `adapted: true` lo distingue de la fuente de verdad."""
    profile = profile or {}
    personal = profile.get("personal", {}) or {}
    blocks = []
    for block in selection.get("selection", []):
        data = block.get("perspective_data") or {}
        blocks.append({
            "section": block["section"],
            "item": block["item_title"],
            "organization": block["item_org"],
            "perspective": block["perspective"],
            "description": data.get("description", ""),
            "skills": data.get("skills", []),
            "tools": data.get("tools", []),
            "relevance_score": block["relevance_score"],
            "matched_skills": block["matched_skills"],
            "matched_domain": block["matched_domain"],
        })
    return {
        "adapted": True,
        "job_title": job.get("title", ""),
        "job_category": (analysis or {}).get("category"),
        "personal": personal,
        "blocks": blocks,
        "combined_skills": selection.get("combined_skills", []),
    }
