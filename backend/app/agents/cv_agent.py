"""CV Agent (§11): selecciona contenido del perfil para la oferta.

NO escribe LaTeX (eso lo hace cv/generator con plantilla fija).
NO inventa nada: solo filtra/ordena lo que ya existe en el perfil
(base_cv.json u otra fuente con la misma forma). Devuelve CVContent
estructurado validado con pydantic.
"""
from __future__ import annotations

import logging

from app.ai.schemas.cv_content import CVContent
from app.analysis.signals import norm

logger = logging.getLogger(__name__)

MAX_EXPERIENCE = 3
MAX_PROJECTS = 3
MAX_SKILLS = 12


def _keywords(text: str) -> set[str]:
    return {w for w in norm(text).split() if len(w) > 3}


def _score_item(item: dict, job_keywords: set[str]) -> int:
    haystack = _keywords(
        " ".join(
            str(item.get(key, ""))
            if not isinstance(item.get(key), list)
            else " ".join(str(v) for v in item.get(key, []))
            for key in ("title", "role", "position", "company",
                        "description", "bullets", "achievements",
                        "technologies", "stack", "name", "summary")
        )
    )
    return len(haystack & job_keywords)


class CVAgent:
    def select_content(
        self, job: dict, analysis: dict, profile: dict
    ) -> CVContent:
        profile = profile or {}
        job_keywords = _keywords(
            f"{job.get('title', '')} {job.get('description', '')} "
            f"{' '.join(analysis.get('evidence', []) or [])}"
        )

        def pick(items, limit: int) -> list[dict]:
            scored = [
                (_score_item(item, job_keywords), idx, item)
                for idx, item in enumerate(items or [])
                if isinstance(item, dict)
            ]
            # Estables: a igual score, conserva el orden del perfil.
            scored.sort(key=lambda row: (-row[0], row[1]))
            return [item for _s, _i, item in scored[:limit]]

        skills = profile.get("skills", {})
        flat_skills: list[str] = []
        if isinstance(skills, dict):
            for group in skills.values():
                if isinstance(group, list):
                    flat_skills.extend(str(s) for s in group)
        elif isinstance(skills, list):
            flat_skills = [str(s) for s in skills]
        # Prioriza skills con overlap, sin inventar ninguna.
        ranked_skills = sorted(
            dict.fromkeys(flat_skills),
            key=lambda s: (
                0 if _keywords(s) & job_keywords else 1, s.lower()
            ),
        )

        personal = profile.get("personal", {}) or {}
        summary = str(profile.get("professional_summary", "") or "")

        return CVContent(
            professional_summary=summary,
            selected_experience=pick(profile.get("experience"), MAX_EXPERIENCE),
            selected_projects=pick(profile.get("projects"), MAX_PROJECTS),
            skills=ranked_skills[:MAX_SKILLS],
            education=[
                e for e in (profile.get("education") or [])
                if isinstance(e, dict)
            ][:4],
        )

    def base_profile(self) -> dict:
        """Lee base_cv.json (fuente de verdad del perfil para CV)."""
        import json

        from app.config import BASE_CV_PATH

        if not BASE_CV_PATH.exists():
            return {}
        try:
            return json.loads(BASE_CV_PATH.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("base_cv.json invalido")
            return {}
