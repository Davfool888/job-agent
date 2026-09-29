"""Prefilter deterministico (§18): decide barato si una oferta merece
analisis profundo (detalle + IA). NO clasifica; solo filtra ruido.

Merece analisis si: alguna señal STRONG, o >=2 MEDIUM distintas,
o el titulo coincide con un rol conocido.
"""
from __future__ import annotations

from app.analysis import signals
from app.analysis.signals import norm
from app.analysis.signals import phrases_found


def prefilter_signals(job: dict) -> dict:
    text = norm(
        f"{job.get('title', '')} {job.get('description', '')} "
        f"{job.get('snippet', '')}"
    )
    title = norm(job.get("title"))

    strong_hits: list[str] = []
    medium_hits: list[str] = []
    for label, aliases, tier in signals.SKILLS:
        if phrases_found(text, aliases):
            if tier == "strong":
                strong_hits.append(label)
            elif tier == "medium":
                medium_hits.append(label)

    title_role = None
    for role, keys in signals.ROLES.items():
        if phrases_found(title, keys["titles"]):
            title_role = role
            break

    deserves = bool(strong_hits or len(medium_hits) >= 2 or title_role)
    return {
        "deserves": deserves,
        "strong": strong_hits[:5],
        "medium": medium_hits[:5],
        "title_role": title_role,
    }


def deserves_deep_analysis(job: dict) -> bool:
    return prefilter_signals(job)["deserves"]
