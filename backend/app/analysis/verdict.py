"""Evaluacion legible oferta-vs-perfil (una sola via, sin IA).

Complementa `match_score` (numero) con dimensiones contrastadas:
tecnicas, blandas, experiencia, puesto y contenido. Funcion pura:
no toca BD, no cambia scores ni umbrales; solo explica. Se calcula
al vuelo en los endpoints de analisis para no persistir nada.
"""
from __future__ import annotations

# Blandas canonicas (las mismas de skills_canonical; lista local para
# no acoplar import circular: analysis <- profile ya existe, pero este
# modulo debe seguir importable sin DB).
SOFT_SKILLS = frozenset({
    "Trabajo en equipo",
    "Comunicación",
    "Liderazgo",
    "Orientación a resultados",
    "Atención al detalle",
    "Pensamiento analítico",
    "Resolución de problemas",
    "Adaptabilidad",
    "Gestión del tiempo",
})

# Bandas del veredicto (alineadas con umbrales CV 75/50 del proyecto).
LEVELS = (
    (75, "muy_compatible", "Muy compatible"),
    (55, "compatible", "Compatible"),
    (40, "parcial", "Parcialmente compatible"),
    (0, "poco_compatible", "Poco compatible"),
)

LEVEL_LABELS = {code: label for _, code, label in LEVELS}


def _canon(text: str) -> str:
    try:
        from app.analysis.skills_canonical import canonicalize_one
        from app.analysis.skills_canonical import canonical_key

        canon = canonicalize_one(str(text or ""))
        return canonical_key(canon) if canon else ""
    except Exception:  # noqa: BLE001
        import re as _re
        import unicodedata as _ud

        plain = "".join(
            c for c in _ud.normalize("NFKD", str(text or "").lower())
            if not _ud.combining(c))
        return _re.sub(r"\s+", " ", plain).strip()


def _canon_label(text: str) -> str:
    try:
        from app.analysis.skills_canonical import canonicalize_one

        return canonicalize_one(str(text or "")) or str(text or "").strip()
    except Exception:  # noqa: BLE001
        return str(text or "").strip()


def split_tech_soft(skills: list | None) -> tuple[list[str], list[str]]:
    """Separa tecnicas/blandas por etiqueta canonica (orden, unicas)."""
    tech: list[str] = []
    soft: list[str] = []
    seen: set[str] = set()
    for raw in (skills or []):
        label = _canon_label(raw)
        if not label:
            continue
        key = _canon(label)
        if not key or key in seen:
            continue
        seen.add(key)
        (soft if label in SOFT_SKILLS else tech).append(label)
    return tech, soft


def _coverage(matched: list, missing: list) -> int | None:
    total = len(matched) + len(missing)
    if not total:
        return None
    return round(100 * len(matched) / total)


def experience_fit(job: dict, analysis: dict,
                   profile_years) -> dict:
    """Contrasta años exigidos vs años del perfil (sin inventar)."""
    required: float | None = None
    required_text = str(analysis.get("experience_required") or "").strip()
    try:
        from app.analysis.fit import parse_experience_required

        blob = " ".join(str(job.get(k) or "") for k in (
            "title", "description", "requirements"))
        required = parse_experience_required(blob)
    except Exception:  # noqa: BLE001
        required = None
    years: float | None = None
    try:
        if profile_years not in (None, ""):
            years = float(profile_years)
    except (TypeError, ValueError):
        years = None
    if required is None and not required_text:
        return {"required_years": None, "profile_years": years,
                "fit": "sin_dato",
                "note": "La oferta no declara experiencia."}
    if required == 0:
        return {"required_years": 0, "profile_years": years,
                "fit": "exento",
                "note": "No exige experiencia previa."}
    if required is None:
        return {"required_years": None, "profile_years": years,
                "fit": "sin_dato",
                "note": f"Declara: {required_text}" if required_text else
                "Sin años precisos."}
    if years is None:
        return {"required_years": required, "profile_years": None,
                "fit": "sin_dato",
                "note": f"Pide {required:g} año(s); tu perfil no declara años."}
    if years >= required + 2:
        fit, note = "sobrado", (
            f"Pide {required:g} año(s) y tienes {years:g}: vas sobrado.")
    elif years >= required:
        fit, note = "justo", (
            f"Pide {required:g} año(s) y tienes {years:g}: cumples justo.")
    else:
        fit, note = "corto", (
            f"Pide {required:g} año(s) y tienes {years:g}: te faltan "
            f"{required - years:g}.")
    return {"required_years": required, "profile_years": years,
            "fit": fit, "note": note}


def role_fit(category: str | None, detected_role: str | None,
             target_roles: list | None) -> dict:
    """Encaje del puesto con tus roles objetivo (contencion simple)."""
    from app.analysis.signals import norm

    targets = [str(t).strip() for t in (target_roles or []) if str(t).strip()]
    cat = norm(category or "")
    matched_target: str | None = None
    for target in targets:
        wanted = norm(target)
        if not wanted:
            continue
        if (wanted and cat and (wanted in cat or cat in wanted)) or (
                detected_role and wanted
                and (wanted in norm(detected_role)
                     or norm(detected_role) in wanted)):
            matched_target = target
            break
    if not targets:
        return {"category": category, "detected_role": detected_role,
                "target_roles": [], "match": None, "matched_target": None,
                "note": "No tienes roles objetivo para comparar."}
    if matched_target:
        return {"category": category, "detected_role": detected_role,
                "target_roles": targets, "match": True,
                "matched_target": matched_target,
                "note": f"Encaja con tu objetivo '{matched_target}'."}
    return {"category": category, "detected_role": detected_role,
            "target_roles": targets, "match": False, "matched_target": None,
            "note": "No coincide con tus roles objetivo."}


def level_for_score(score) -> tuple[str, str]:
    """(codigo, etiqueta) del veredicto segun el puntaje."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "sin_datos", "Sin analizar"
    for floor, code, label in LEVELS:
        if value >= floor:
            return code, label
    return "poco_compatible", "Poco compatible"


def build_fit_report(job: dict, analysis: dict, profile: dict | None,
                     rich: dict | None = None) -> dict:
    """Reporte legible oferta-vs-perfil. Nunca lanza (devuelve minimo)."""
    try:
        return _build(job, analysis, profile or {}, rich or {})
    except Exception:  # noqa: BLE001
        score = (analysis or {}).get("match_score")
        code, label = level_for_score(score)
        return {"level": code, "label": label, "score": score,
                "dimensions": {}, "strengths": [], "gaps": [],
                "reasons": []}


def _build(job: dict, analysis: dict, profile: dict, rich: dict) -> dict:
    score = analysis.get("match_score")
    code, label = level_for_score(score)
    matched = list(analysis.get("matched_skills") or [])
    missing = list(analysis.get("missing_skills") or [])
    tech_matched, soft_matched = split_tech_soft(matched)
    tech_missing, soft_missing = split_tech_soft(missing)
    tech_cov = _coverage(tech_matched, tech_missing)
    soft_cov = _coverage(soft_matched, soft_missing)

    flat_tech = [_canon_label(s) for s in (profile.get("skills") or [])]
    flat_tech = [s for s in flat_tech if s]
    rich_tech = [_canon_label(s) for s in (rich.get("technical_skills") or [])]
    rich_tech = [s for s in rich_tech if s]
    rich_soft = [_canon_label(s) for s in (rich.get("soft_skills") or [])]
    rich_soft = [s for s in rich_soft if s]
    years = rich.get("years_experience")
    if years in (None, ""):
        years = profile.get("years_experience")
    targets = list(profile.get("target_roles") or []) or list(
        rich.get("target_roles") or [])

    exp = experience_fit(job, analysis, years)
    role = role_fit(analysis.get("category"), analysis.get("detected_role"),
                    targets)

    strengths: list[str] = []
    gaps: list[str] = []
    if tech_matched:
        strengths.append(
            f"Técnicas que cumples ({len(tech_matched)}): "
            + ", ".join(tech_matched[:6])
            + ("…" if len(tech_matched) > 6 else ""))
    if soft_matched:
        strengths.append(
            f"Blandas que cumples ({len(soft_matched)}): "
            + ", ".join(soft_matched[:6])
            + ("…" if len(soft_matched) > 6 else ""))
    if exp["fit"] in ("sobrado", "justo", "exento"):
        strengths.append("Experiencia: " + exp["note"])
    if role["match"]:
        strengths.append("Puesto: " + role["note"])
    if tech_missing:
        gaps.append(
            f"Técnicas que te faltan ({len(tech_missing)}): "
            + ", ".join(tech_missing[:6])
            + ("…" if len(tech_missing) > 6 else ""))
    if soft_missing:
        gaps.append(
            f"Blandas que te faltan ({len(soft_missing)}): "
            + ", ".join(soft_missing[:6])
            + ("…" if len(soft_missing) > 6 else ""))
    if exp["fit"] == "corto":
        gaps.append("Experiencia: " + exp["note"])
    if role["match"] is False:
        gaps.append("Puesto: " + role["note"])

    reasons = [f"{label} ({None if score is None else round(float(score))}%)."]
    if tech_cov is not None:
        reasons.append(f"Cubres {tech_cov}% de lo técnico pedido.")
    if exp["fit"] != "sin_dato":
        reasons.append(exp["note"])
    if role["match"] is not None:
        reasons.append(role["note"])

    breakdown = analysis.get("score_breakdown") or {}
    return {
        "level": code,
        "label": label,
        "score": score,
        "dimensions": {
            "tecnicas": {"matched": tech_matched, "missing": tech_missing,
                         "coverage": tech_cov},
            "blandas": {"matched": soft_matched, "missing": soft_missing,
                        "coverage": soft_cov},
            "experiencia": exp,
            "puesto": role,
            "contenido": {k: breakdown.get(k) for k in (
                "title", "skills", "responsibilities", "tools")
                if isinstance(breakdown, dict)},
        },
        "profile_snapshot": {
            "technical_skills": rich_tech or [s for s in flat_tech
                                              if s not in SOFT_SKILLS][:30],
            "soft_skills": rich_soft,
            "years_experience": years,
            "target_roles": targets[:10],
        },
        "strengths": strengths,
        "gaps": gaps,
        "reasons": reasons,
    }
