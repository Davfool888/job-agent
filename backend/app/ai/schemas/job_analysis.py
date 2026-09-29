"""Schemas pydantic para validar respuestas de proveedores IA."""
from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field


class JobAnalysisResult(BaseModel):
    detected_role: str | None = None
    category: str = "OTHER"
    match_score: float = Field(ge=0, le=100, default=0)
    evidence: list[str] = Field(default_factory=list)
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    experience_required: str | None = None
    summary: str = ""


class CVContent(BaseModel):
    professional_summary: str = ""
    selected_experience: list[dict] = Field(default_factory=list)
    selected_projects: list[dict] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
