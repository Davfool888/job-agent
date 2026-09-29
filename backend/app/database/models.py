from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text

from app.database.connection import Base


# Estados del ciclo de vida de una oferta. El frontend solo usa estos
# valores; el default 'new' mantiene compatibilidad con filas antiguas.
JOB_STATUSES = (
    "new",
    "kept",
    "discarded",
    "opened",
    "applied",
)


class Job(Base):

    __tablename__ = "jobs"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String(300),
        nullable=False
    )

    company = Column(
        String(300),
        nullable=True
    )

    location = Column(
        String(300),
        nullable=True
    )

    url = Column(
        String(1000),
        nullable=False,
        unique=True
    )

    description = Column(
        Text,
        nullable=True
    )

    source = Column(
        String(100),
        nullable=False,
        default="computrabajo"
    )

    search_query = Column(
        String(300),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # --- Gestion (frontend). Todo nullable/default para no romper filas
    # existentes ni el scraper actual. ---

    status = Column(
        String(50),
        nullable=False,
        default="new",
    )

    discard_reason = Column(
        String(200),
        nullable=True,
    )

    discard_note = Column(
        Text,
        nullable=True,
    )

    decided_at = Column(
        DateTime,
        nullable=True,
    )

    applied_at = Column(
        DateTime,
        nullable=True,
    )

    application_status = Column(
        String(50),
        nullable=True,
    )

    # Analisis de coincidencia (lo escribe el agente cuando exista;
    # el frontend NUNCA inventa estos valores).
    match_score = Column(
        Float,
        nullable=True,
    )

    matched_skills = Column(
        Text,  # JSON array
        nullable=True,
    )

    missing_skills = Column(
        Text,  # JSON array
        nullable=True,
    )

    # --- Tiempo de publicacion (extraido de cada fuente) ---

    published_text = Column(
        String(200),
        nullable=True,
    )

    published_at = Column(
        DateTime,
        nullable=True,
    )

    # --- Republicacion: misma oferta (titulo+empresa+ubicacion)
    # publicada con otra URL. `times_seen` = N.o de publicaciones
    # distintas con la misma huella; se actualiza en todo el grupo. ---

    fingerprint = Column(
        String(64),
        nullable=True,
        index=True,
    )

    times_seen = Column(
        Integer,
        nullable=False,
        default=1,
    )

    last_seen_at = Column(
        DateTime,
        nullable=True,
    )

    # --- Descubrimiento y analisis por capas (analysis/discovery).
    # Todo nullable/default: filas antiguas quedan como "sin analizar". ---

    detected_role = Column(
        String(100),
        nullable=True,
    )

    category = Column(
        String(50),
        nullable=True,
    )

    evidence = Column(
        Text,  # JSON array de etiquetas
        nullable=True,
    )

    discovered_by = Column(
        Text,  # JSON array de slugs de query
        nullable=True,
    )

    experience_required = Column(
        String(200),
        nullable=True,
    )

    # --- Esquema normalizado §14-§16 (todo nullable/default) ---

    external_id = Column(
        String(200),
        nullable=True,
        index=True,
    )

    requirements = Column(
        Text,  # JSON array
        nullable=True,
    )

    responsibilities = Column(
        Text,  # JSON array
        nullable=True,
    )

    sector = Column(
        String(200),
        nullable=True,
    )

    modality = Column(
        String(100),
        nullable=True,
    )

    salary = Column(
        String(200),
        nullable=True,
    )

    content_hash = Column(
        String(64),
        nullable=True,
        index=True,
    )

    cv_generated = Column(
        Integer,
        nullable=False,
        default=0,
    )

    cv_path = Column(
        String(500),
        nullable=True,
    )


class Profile(Base):
    """Perfil profesional singleton (id=1). `data` es un JSON con
    info personal, habilidades y preferencias que usara el agente."""

    __tablename__ = "profile"

    id = Column(Integer, primary_key=True)

    data = Column(Text, nullable=False, default="{}")

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
