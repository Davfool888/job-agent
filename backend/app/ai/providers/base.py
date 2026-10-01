"""Interfaz comun de proveedores IA (§9)."""
from __future__ import annotations

from abc import ABC
from abc import abstractmethod


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        """False si falta API key, SDK u otro requisito."""

    @abstractmethod
    def analyze_job(self, job: dict, profile: dict) -> dict:
        """Devuelve dict validable como JobAnalysisResult."""

    @abstractmethod
    def generate_cv_content(
        self, job: dict, analysis: dict, profile: dict,
        reference_cvs: list | None = None,
    ) -> dict:
        """Devuelve dict validable como CVContent."""
