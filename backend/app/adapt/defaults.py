"""Unica fuente de defaults de pdf_config.

Antes vivian en tres sitios con valores DIVERGENTES (renderer usaba
margenes 18/18/15/15 cuando faltaba la clave; coerce y servicio, 25
APA). Todos los modulos leen de aqui; el servicio/coerce sigue
rellenando la config antes de entregar al resto.
"""
from __future__ import annotations

SECTION_ORDER_DEFAULT = [
    "summary", "experience", "education", "projects",
    "skills", "soft_skills", "languages",
    "other_studies", "other_knowledge",
]

KNOWN_SECTIONS = tuple(SECTION_ORDER_DEFAULT)

ALLOWED_DATE_FORMATS = ("MMM YYYY", "MM/YYYY", "MM/YY", "MMMM YYYY",
                        "YYYY-MM")

ALLOWED_FONTS = ("georgia", "times", "arial")

ALLOWED_SIZES = (10, 11, 12, 14, 16)

FONT_MAP = {
    "georgia": '"Georgia", "Times New Roman", serif',
    "times": '"Times New Roman", Georgia, serif',
    "arial": '"Arial", "Helvetica Neue", Helvetica, sans-serif',
}

DEFAULT_PDF_CONFIG: dict = {
    "font_family": "georgia",
    "font_size_pt": 11,
    "section_order": list(SECTION_ORDER_DEFAULT),
    "date_format": "MMM YYYY",
    "show_skill_chips": True,
    "compact_mode": False,
    "header_style": "classic",
    "section_divider": "line",
    "margin_top_mm": 25,
    "margin_bottom_mm": 25,
    "margin_left_mm": 25,
    "margin_right_mm": 25,
    "section_spacing_pt": 14,
    "accent_color": "#000000",
    "max_projects": 0,
    "max_experiences": 0,
    "max_bullets": 0,
    "profile_length": "full",
    "show_soft_skills": True,
    "show_courses": True,
    "show_languages": True,
    "show_links": True,
    "ai_rewrite_bullets": False,
    "max_pages": 0,
}

# Topes historicos cuando el limite es 0/ausente (selector).
LIMIT_DEFAULTS = {
    "max_experiences": 3,
    "max_projects": 3,
    "max_certifications": 3,
    "max_education": 2,
    "max_skills": 12,
}
