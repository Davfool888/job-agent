"""Proveedor local deterministico (siempre disponible, sin red ni keys).

Garantiza que el pipeline funcione gratis/offline: el analisis usa el
motor de reglas y el CV usa seleccion por overlap contra base_cv.json.
Es el ultimo eslabon del fallback A -> B -> C.
"""
from __future__ import annotations

from app.ai.providers.base import AIProvider


class RuleBasedProvider(AIProvider):
    name = "rule_based"

    def available(self) -> bool:
        return True

    def analyze_job(self, job: dict, profile: dict) -> dict:
        from app.analysis.scorer import analyze_job as deterministic

        result = deterministic(job, profile or {})
        return {
            "detected_role": result["detected_role"],
            "category": result["category"],
            "match_score": result["match_score"],
            "evidence": result["evidence"],
            "matching_skills": result["matched_skills"],
            "missing_skills": result["missing_skills"],
            "experience_required": result["experience_required"],
            "summary": (
                f"Analisis deterministico: {result['category']} "
                f"({result['match_score']}%)."
            ),
        }

    def generate_cv_content(
        self, job: dict, analysis: dict, profile: dict
    ) -> dict:
        from app.agents.cv_agent import CVAgent

        return CVAgent().select_content(job, analysis, profile).model_dump()
