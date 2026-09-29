"""Job Analysis Agent (§5): rol real + scoring + matching.

Usa el motor deterministico (analysis/scorer + services/matching)
y reserva el AI Router para casos ambiguos o enriquecimiento.
Comunicacion con otros agentes: JSON estructurado (ai/schemas).
"""
from __future__ import annotations

import logging

from app.agents.job_analyzer import JobAnalyzer

logger = logging.getLogger(__name__)

# Ambiguo = score medio o rol OTHER con señales: candidato a IA.
AMBIGUOUS_MIN = 35
AMBIGUOUS_MAX = 55


class JobAnalysisAgent:
    def __init__(self):
        self.deterministic = JobAnalyzer()

    def is_ambiguous(self, result: dict) -> bool:
        score = result.get("match_score") or 0
        return (
            AMBIGUOUS_MIN <= score < AMBIGUOUS_MAX
        ) or (
            result.get("category") == "OTHER" and score >= 30
        )

    def analyze(
        self, job: dict, profile: dict | None = None, use_ai: bool = False
    ) -> dict:
        """Analisis deterministico; si use_ai=True y el caso es ambiguo,
        intenta enriquecer via AI Router (no falla si no hay proveedor)."""
        result = self.deterministic.analyze(job, profile or {})

        if use_ai and self.is_ambiguous(result):
            try:
                from app.ai.router import get_router

                router = get_router()
                if router.available():
                    enriched = router.analyze_job(job, profile or {})
                    result["ai_enriched"] = True
                    result["ai_provider"] = enriched.get("provider")
                    ai_role = (enriched.get("analysis") or {}).get(
                        "detected_role"
                    )
                    if ai_role and result["category"] == "OTHER":
                        result["ai_suggested_role"] = ai_role
            except Exception as error:  # noqa: BLE001
                logger.warning("Enriquecimiento IA fallo: %s", error)

        return result
