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

        # Relevancia por perspectiva (si el perfil es modular): mapea
        # item -> mejor perspectiva para esta vacante.
        perspective_rank: dict[tuple[str, int], tuple[float, dict]] = {}
        try:
            from app.profile.perspectives import SECTIONS
            from app.profile.perspectives import select_perspectives

            selection = select_perspectives(
                profile, job, analysis or {}, max_total=12, min_score=0.0
            )
            for block in selection["selection"]:
                key = (block["section"], block["item_index"])
                data = block.get("perspective_data") or {}
                current = perspective_rank.get(key)
                if current is None or block["relevance_score"] > current[0]:
                    perspective_rank[key] = (
                        block["relevance_score"], data
                    )
        except Exception:
            logger.debug("seleccion por perspectivas no disponible")

        def pick(items, limit: int, section: str) -> list[dict]:
            scored = []
            for idx, item in enumerate(items or []):
                if not isinstance(item, dict):
                    continue
                rank = perspective_rank.get((section, idx))
                if rank is not None:
                    score = 1000 + rank[0]  # perspectivas mandan
                else:
                    score = _score_item(item, job_keywords)
                scored.append((score, idx, item))
            # Estables: a igual score, conserva el orden del perfil.
            scored.sort(key=lambda row: (-row[0], row[1]))
            picked = []
            for _s, _i, item in scored[:limit]:
                item = dict(item)
                rank = perspective_rank.get((section, _i))
                if rank is not None and rank[1].get("description"):
                    # La perspectiva aporta el enfoque como primer bullet;
                    # los originales se conservan debajo (nada se inventa).
                    item["perspective"] = rank[1].get("label", "")
                    original = list(item.get("bullets") or [])
                    item["bullets"] = (
                        [rank[1]["description"]] + original
                    )
                picked.append(item)
            return picked

        skills = profile.get("skills", {})
        flat_skills: list[str] = []
        if isinstance(skills, dict):
            for group in skills.values():
                if isinstance(group, list):
                    flat_skills.extend(str(s) for s in group)
        elif isinstance(skills, list):
            flat_skills = [str(s) for s in skills]
        # Skills globales tecnicas/blandas (perfil estructurado).
        for key in ("technical_skills", "soft_skills"):
            values = profile.get(key)
            if isinstance(values, list):
                flat_skills.extend(str(s) for s in values)
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
            selected_experience=pick(
                profile.get("experience"), MAX_EXPERIENCE, "experience"),
            selected_projects=pick(
                profile.get("projects"), MAX_PROJECTS, "projects"),
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
