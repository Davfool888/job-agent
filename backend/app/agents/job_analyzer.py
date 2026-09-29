"""Analizador de ofertas: pipeline deterministico + hook IA opcional.

§19: primero keywords/reglas/scoring (gratis, sin llamadas). La IA
(Gemini) queda reservada para casos ambiguos o enriquecimiento y SOLO
se usa si hay API key configurada y se pide explicitamente.
"""
from __future__ import annotations

from app.analysis.scorer import analyze_job
from app.config import GEMINI_API_KEY


class JobAnalyzer:
    """API compatible con la version anterior (stub), ahora funcional."""

    def __init__(self):
        self.api_key = GEMINI_API_KEY

    def analyze(self, job: dict, profile: dict | None = None) -> dict:
        """Analisis deterministico completo de la oferta.

        Devuelve: match_score, detected_role, category, evidence,
        matched_skills, missing_skills, experience_required,
        role_matches_goal, score_breakdown.
        """
        result = analyze_job(job, profile or {})
        result.update(
            {
                "job_title": job.get("title"),
                "company": job.get("company"),
                "relevant": result["match_score"] >= 40
                or result["category"] != "OTHER",
                "ai_enriched": False,
            }
        )
        return result

    def ai_available(self) -> bool:
        return bool(self.api_key)
