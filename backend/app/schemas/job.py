from datetime import datetime
import json

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator


class JobBase(BaseModel):

    title: str

    company: str | None = None

    location: str | None = None

    url: str

    description: str | None = None

    source: str = "computrabajo"

    search_query: str | None = None


class JobResponse(JobBase):
    """Refleja la tabla `jobs`. Los campos de gestion/analisis son
    opcionales porque las filas antiguas y el scraper no los proveen."""

    id: int

    created_at: datetime

    status: str = "new"

    discard_reason: str | None = None

    discard_note: str | None = None

    decided_at: datetime | None = None

    applied_at: datetime | None = None

    application_status: str | None = None

    match_score: float | None = None

    matched_skills: list[str] = Field(default_factory=list)

    missing_skills: list[str] = Field(default_factory=list)

    published_text: str | None = None

    published_at: datetime | None = None

    external_id: str | None = None

    requirements: list[str] = Field(default_factory=list)

    responsibilities: list[str] = Field(default_factory=list)

    sector: str | None = None

    modality: str | None = None

    salary: str | None = None

    content_hash: str | None = None

    cv_generated: bool = False

    cv_path: str | None = None

    fingerprint: str | None = None

    times_seen: int = 1

    last_seen_at: datetime | None = None

    detected_role: str | None = None

    category: str | None = None

    evidence: list[str] = Field(default_factory=list)

    discovered_by: list[str] = Field(default_factory=list)

    experience_required: str | None = None

    @field_validator(
        "matched_skills",
        "missing_skills",
        "evidence",
        "discovered_by",
        "requirements",
        "responsibilities",
        mode="before",
    )
    @classmethod
    def _parse_json_lists(cls, value):
        # En BD se guardan como TEXT con JSON; el scraper las deja vacias.
        if not value:
            return []
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []

    model_config = ConfigDict(from_attributes=True)


class JobStatusUpdate(BaseModel):
    """Body de PATCH /jobs/{id}/status."""

    status: str = Field(
        ...,
        description=(
            "new | kept | discarded | opened | applied"
        ),
    )

    discard_reason: str | None = None

    discard_note: str | None = None

    application_status: str | None = None
