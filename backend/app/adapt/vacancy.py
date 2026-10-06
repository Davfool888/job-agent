"""Analisis de la vacante por niveles de prioridad (deterministico).

Extrae: cargo, requisitos (estructurados + texto), keywords en tres
niveles (alta: titulo y requisitos explicitos; media: vocabulario en
descripcion; baja: resto relevante), sector, nivel y Seniority. Sin
LLM: todo sale literalmente de la oferta.
"""
from __future__ import annotations

_SECTORS: list[tuple[str, tuple[str, ...]]] = [
    ("financiero", ("banco", "bancario", "financiera", "finanzas",
                    "credito", "seguros", "bolsa", "fintech")),
    ("retail", ("retail", "ventas", "comercial", "tienda", "ecommerce",
                "consumo masivo")),
    ("tecnologia", ("software", "tecnologia", "startup", "saas",
                    "desarrollo de software")),
    ("salud", ("salud", "hospital", "clinica", "farmaceutica")),
    ("logistica", ("logistica", "transporte", "cadena de suministro",
                   "almacen")),
    ("educacion", ("educacion", "universidad", "colegio", "academia")),
    ("gobierno", ("gobierno", "publico", "estado", "ministerio")),
    ("industria", ("industria", "manufactura", "planta", "fabrica")),
]


def _norm(text: str | None) -> str:
    from app.analysis.signals import norm

    return norm(text)


def _offer_text(offer: dict, keys: tuple[str, ...]) -> str:
    parts = []
    for key in keys:
        value = (offer or {}).get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def _vocab_hits(text_norm: str) -> list[str]:
    """Terminos del vocabulario presentes, ordenados por aparicion."""
    from app.adapt.matcher import _vocab
    from app.analysis.signals import norm, phrases_found

    found: list[str] = []
    for label, aliases in _vocab():
        if phrases_found(text_norm, [label, *aliases]) \
                and norm(label) not in {norm(f) for f in found}:
            found.append(label)
    return found


def analyze_vacancy(offer: dict) -> dict:
    """Devuelve el analisis estructurado de la vacante."""
    from app.adapt.matcher import explicit_required_skills
    from app.analysis.signals import norm

    offer = offer or {}
    role = str(offer.get("title") or "").strip()
    title_norm = _norm(role)
    desc_norm = _norm(_offer_text(offer, ("description",)))
    req_norm = _norm(_offer_text(
        offer, ("requirements", "responsibilities")))

    explicit = explicit_required_skills(offer)
    title_hits = _vocab_hits(title_norm)
    req_hits = [t for t in _vocab_hits(req_norm)
                if norm(t) not in {norm(e) for e in explicit}]
    desc_hits = [t for t in _vocab_hits(desc_norm)
                 if norm(t) not in {norm(e) for e in explicit}
                 and norm(t) not in {norm(t2) for t2 in title_hits + req_hits}]

    high = explicit + [t for t in title_hits
                       if norm(t) not in {norm(e) for e in explicit}]
    medium = req_hits
    low = desc_hits

    sector = None
    blob = f"{title_norm} {desc_norm} {_norm(str(offer.get('company') or ''))}"
    for sector_id, keywords in _SECTORS:
        if any(k in blob for k in keywords):
            sector = sector_id
            break

    try:
        from app.analysis.fit import detect_seniority

        seniority = detect_seniority(f"{role} {offer.get('description')}")
    except Exception:  # noqa: BLE001
        seniority = None

    return {
        "role": role,
        "requirements": explicit,
        "keywords_high": high,
        "keywords_medium": medium,
        "keywords_low": low,
        "keywords_all": high + medium + low,
        "title_keywords": title_hits,
        "sector": sector,
        "seniority": seniority,
    }
