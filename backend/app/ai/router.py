"""AI Router (§8): independiente del proveedor.

Uso: get_router().analyze_job(job, profile) sin saber que proveedor
responde. Cadena A -> B -> C con manejo de errores, timeouts,
rate limits, respuestas invalidas y JSON invalido (validados con
pydantic antes de aceptar).
"""
from __future__ import annotations

import logging

from app.ai.schemas.cv_content import CVContent
from app.ai.schemas.job_analysis import JobAnalysisResult

logger = logging.getLogger(__name__)


class AIRouter:
    def __init__(self, providers=None):
        if providers is not None:
            self.providers = list(providers)
        else:
            from app.ai.providers.gemini import GeminiProvider
            from app.ai.providers.openai_compat import OpenAICompatProvider
            from app.ai.providers.rule_based import RuleBasedProvider

            by_name = {
                "gemini": GeminiProvider(),
                "openai_compat": OpenAICompatProvider(),
                "rule_based": RuleBasedProvider(),
            }
            from app.config import AI_PROVIDER_ORDER

            self.providers = [
                by_name[name]
                for name in AI_PROVIDER_ORDER
                if name in by_name
            ] or [RuleBasedProvider()]

    def available(self) -> bool:
        return any(p.available() for p in self.providers)

    def providers_status(self) -> list[dict]:
        return [
            {"provider": p.name, "available": p.available()}
            for p in self.providers
        ]

    def _attempt(self, method: str, payload: dict) -> dict:
        """Intenta cada proveedor en orden; el primero que devuelva
        JSON valido gana. Si ninguno responde, lanza RuntimeError."""
        errors: list[str] = []
        for provider in self.providers:
            if not provider.available():
                errors.append(f"{provider.name}: no disponible")
                continue
            try:
                fn = getattr(provider, method)
                raw = fn(**payload)
                if method == "analyze_job":
                    validated = JobAnalysisResult.model_validate(raw)
                else:
                    validated = CVContent.model_validate(raw)
                return {
                    "provider": provider.name,
                    **validated.model_dump(),
                }
            except Exception as error:  # noqa: BLE001
                # timeout, rate limit, HTTP, JSON invalido, validacion...
                message = f"{provider.name}: {type(error).__name__}: {error}"
                logger.warning("AI provider fallo: %s", message[:300])
                errors.append(message[:300])
                continue
        raise RuntimeError(
            "Ningun proveedor IA respondio: " + " | ".join(errors)
        )

    def analyze_job(self, job: dict, profile: dict) -> dict:
        return self._attempt("analyze_job", {"job": job, "profile": profile})

    def generate_cv_content(
        self, job: dict, analysis: dict, profile: dict
    ) -> dict:
        return self._attempt(
            "generate_cv_content",
            {"job": job, "analysis": analysis, "profile": profile},
        )


_router: AIRouter | None = None


def get_router() -> AIRouter:
    global _router
    if _router is None:
        _router = AIRouter()
    return _router
