"""Filtros de ajuste oferta <-> configuracion (titulo + descripcion).

Regla de jerarquia: cada variable solo descarta ante contradiccion
EXPLICITA en el texto (titulo + descripcion + salario declarado).
Si la oferta no trae el dato, pasa y se evalua la siguiente
variable. Sin config (todo None) no filtra nada.
"""
from __future__ import annotations

import re
import unicodedata

_SENIORITY_RANK = {"trainee": 0, "junior": 1, "mid": 2, "senior": 3}

# Orden: el mas especifico primero ('semi-senior' contiene 'senior').
_SENIORITY_PATTERNS: list[tuple[str, str]] = [
    ("trainee", r"practicante|pasante|pasantia|intern\b|trainee|practicas"),
    ("mid", r"semi[\s-]?senior|semisenior|\bssr\b|mid[\s-]?level|semi[\s-]?sr"),
    ("senior", r"senior|\bsr\b|leader|lead\b|l[ií]der"),
    ("junior", r"junior|\bjr\b"),
]


def _norm(text: str | None) -> str:
    text = unicodedata.normalize(
        "NFKD", str(text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def offer_text(job) -> str:
    """Titulo + descripcion + salario declarado (lo que ve el filtro)."""
    if isinstance(job, dict):
        parts = [job.get("title"), job.get("description"),
                 job.get("salary")]
    else:
        parts = [getattr(job, "title", ""),
                 getattr(job, "description", ""),
                 getattr(job, "salary", "")]
    return " ".join(str(p or "") for p in parts)


def detect_seniority(text: str) -> str | None:
    lowered = _norm(text)
    for level, pattern in _SENIORITY_PATTERNS:
        if re.search(pattern, lowered):
            return level
    return None


_UNIT = r"(?:a[nñ]os?|anos?|exp(?:eriencia)?\.?|yrs?|years?)"

_EXP_PATTERNS = [
    # "sin experiencia" / "no requiere experiencia" -> 0.
    (re.compile(r"sin experiencia|no (?:se )?requiere experiencia|"
                r"no es necesaria experiencia"), lambda m: 0.0),
    # "año y medio de experiencia" -> 1.5.
    (re.compile(r"a[nñ]o\s+y\s+medio"), lambda m: 1.5),
    # "de 2 a 4 años" / "entre 2 y 4 años" -> minimo 2.
    (re.compile(r"(?:de|entre)\s+(\d+(?:[.,]\d+)?)\s+(?:a|y)\s+"
                r"\d+(?:[.,]\d+)?\s*" + _UNIT),
     lambda m: float(m.group(1).replace(",", "."))),
    # "+2 años", "2+ años", "mínimo 2 años", "2 años de exp".
    (re.compile(r"[+]\s*(\d+(?:[.,]\d+)?)\s*" + _UNIT),
     lambda m: float(m.group(1).replace(",", "."))),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*[+]\s*" + _UNIT),
     lambda m: float(m.group(1).replace(",", "."))),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*" + _UNIT),
     lambda m: float(m.group(1).replace(",", "."))),
    # "6 meses de experiencia" -> 0.5.
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*meses?(?:\s+de experiencia)?"),
     lambda m: round(float(m.group(1).replace(",", ".")) / 12, 2)),
]


def _words_to_years_safe(text: str) -> float | None:
    try:
        from app.profile.schema import _words_to_years

        return _words_to_years(text)
    except Exception:  # noqa: BLE001
        return None


def parse_experience_required(text: str) -> float | None:
    """Años exigidos o None si no se declaran.

    Digitos, palabras ('dos años', 'dos años y medio') y
    abreviaturas ('2 exp', '+2 años exp'), en titulo o descripcion.
    """
    lowered = _norm(text)
    for pattern, build in _EXP_PATTERNS:
        match = pattern.search(lowered)
        if match:
            try:
                return build(match)
            except (TypeError, ValueError):
                continue
    # "dos años de experiencia": palabras antes de la unidad.
    for match in re.finditer(r"([a-z\s]{1,30}?)\s*" + _UNIT, lowered):
        value = _words_to_years_safe(match.group(1))
        if value is not None:
            return value
    return None


def _to_number(token: str) -> float | None:
    try:
        return float(token.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parse_salary_range(text: str, smmlv: int) -> tuple[float | None,
                                                      float | None] | None:
    """(min, max) en COP o None si no hay salario declarable.

    Acepta $3.500.000, $3,500,000, rangos, 'millones', '3.5M' y
    '2 SMMLV'. USD/otra moneda -> None (no se convierte, no filtra).
    """
    raw = str(text or "")
    lowered = _norm(raw)
    if not raw.strip():
        return None
    if re.search(r"\b(usd|dolar|dollar|usd\$)\b", lowered):
        return None
    multi = 1_000_000 if ("millon" in lowered or re.search(
        r"\b\d+(?:[.,]\d+)?\s*m\b", lowered)) else 1
    smmlv_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:smmlv|salarios?\s+m[ií]nimos?)", lowered)
    if smmlv_match:
        value = _to_number(smmlv_match.group(1))
        if value is not None:
            total = value * smmlv
            return total, total
    if "smmlv" in lowered or "salario minimo" in lowered:
        return float(smmlv), float(smmlv)
    numbers = re.findall(r"\d[\d.,]*", raw)
    values = [v for v in (_to_number(t) for t in numbers) if v is not None]
    # Descarta años/fechas sueltas (2024, 2026) salvo montos claros.
    values = [v for v in values if v >= 100_000 or multi > 1]
    if not values:
        return None
    if not ("$" in raw or "cop" in lowered or "peso" in lowered
            or multi > 1):
        return None
    if len(values) >= 2:
        low, high = values[0] * multi, values[1] * multi
    else:
        low = high = values[0] * multi
    if low > high:
        low, high = high, low
    return low, high


_CONTRACT_PATTERNS: list[tuple[str, str]] = [
    ("obra_labor", r"obra\s+o\s+labor|obra/labor|por\s+obra|"
                   r"labor\s+contratada|duraci[oó]n\s+de\s+la\s+obra"),
    ("indefinido", r"t[eé]rmino\s+indefinido|contrato\s+indefinido|"
                   r"\bindefinido\b|contrato\s+a\s+t[eé]rmino\s+indefinido"),
    ("aprendizaje", r"contrato\s+de\s+aprendizaje|\baprendizaje\b|"
                    r"\baprendiz\b|aprendices\b"),
    ("fijo", r"t[eé]rmino\s+fijo|contrato\s+fijo|\bfijo\b|"
             r"temporal|por\s+temporada"),
    ("prestacion", r"prestaci[oó]n\s+de\s+servicios|contratista|"
                   r"freelance|independiente|por\s+honorarios"),
]


def detect_contracts(text: str) -> set[str]:
    """Tipos mencionados (vacio = no declara)."""
    lowered = _norm(text)
    return {cid for cid, pattern in _CONTRACT_PATTERNS
            if re.search(pattern, lowered)}


def check_job(job, config: dict, smmlv: int) -> tuple[bool, str | None]:
    """(pasa, motivo_descarte). Solo descarta ante contradiccion."""
    text = offer_text(job)

    want_level = (config or {}).get("seniority")
    if want_level:
        found = detect_seniority(text)
        if found and _SENIORITY_RANK[found] > _SENIORITY_RANK[want_level]:
            return False, "seniority"

    want_years = (config or {}).get("experience_years")
    if want_years not in (None, ""):
        required = parse_experience_required(text)
        if required is not None and required > float(want_years):
            return False, "experience"

    want_min = (config or {}).get("salary_min_cop")
    want_max = (config or {}).get("salary_max_cop")
    if want_min not in (None, "") or want_max not in (None, ""):
        salary = parse_salary_range(text, smmlv)
        if salary is not None:
            offer_min, offer_max = salary
            if want_min not in (None, "") \
                    and offer_max < float(want_min):
                return False, "salary"
            if want_max not in (None, "") \
                    and offer_min > float(want_max):
                return False, "salary"

    want_contracts = list((config or {}).get("contract_types") or [])
    if want_contracts:
        mentioned = detect_contracts(text)
        if mentioned and mentioned.isdisjoint(want_contracts):
            return False, "contract"

    return True, None


def apply_fit(jobs: list, config: dict, smmlv: int) -> tuple[list, dict]:
    """Filtra por ajuste. Devuelve (aptas, conteo_por_motivo)."""
    if not any([(config or {}).get("seniority"),
                (config or {}).get("experience_years") not in (None, ""),
                (config or {}).get("salary_min_cop") not in (None, ""),
                (config or {}).get("salary_max_cop") not in (None, ""),
                (config or {}).get("contract_types")]):
        return list(jobs), {}
    kept: list = []
    discarded: dict[str, int] = {}
    for job in jobs:
        ok, reason = check_job(job, config, smmlv)
        if ok:
            kept.append(job)
        else:
            discarded[reason or "other"] = discarded.get(
                reason or "other", 0) + 1
    return kept, discarded
