"""Configuracion de busqueda por niveles jerarquicos (global/perfil).

Jerarquia de resolucion: perfil > global (Dashboard y base de las
automaticas) > sin filtro (None). Cada variable se hereda por
separado: un perfil puede fijar salario y heredar el resto.

Niveles:
- seniority: trainee|junior|mid|senior (rango: la oferta debe pedir
  como maximo el nivel propio; sin dato en la oferta -> pasa).
- experience_years: años propios (0.5, 1..5, PLUS_YEARS=solo 5+).
- salary_min_cop: piso en COP (SMMLV o bandas); la oferta debe pagar
  al menos eso o no declarar salario.
- contract_types: subset de obra_labor|indefinido|aprendizaje; la
  oferta debe mencionar uno o no mencionar ninguno.
"""
from __future__ import annotations

import json
from datetime import datetime

PLUS_YEARS = 99.0  # "+5 años o más": ninguna exigencia lo supera.

SENIORITY_LEVELS = [
    {"id": "trainee", "label": "Practicante / Trainee", "rank": 0},
    {"id": "junior", "label": "Junior", "rank": 1},
    {"id": "mid", "label": "Semi-senior", "rank": 2},
    {"id": "senior", "label": "Senior", "rank": 3},
]
SENIORITY_IDS = {item["id"] for item in SENIORITY_LEVELS}

EXPERIENCE_BUCKETS = [
    {"years": 0.5, "label": "6 meses"},
    {"years": 1.0, "label": "1 año"},
    {"years": 2.0, "label": "2 años"},
    {"years": 3.0, "label": "3 años"},
    {"years": 4.0, "label": "4 años"},
    {"years": 5.0, "label": "5 años"},
    {"years": PLUS_YEARS, "label": "+5 años"},
]
EXPERIENCE_VALUES = {item["years"] for item in EXPERIENCE_BUCKETS}

CONTRACT_TYPES = [
    {"id": "obra_labor", "label": "Obra o labor"},
    {"id": "indefinido", "label": "Término indefinido"},
    {"id": "aprendizaje", "label": "Contrato de aprendizaje"},
]
CONTRACT_IDS = {item["id"] for item in CONTRACT_TYPES}


def _cop_label(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")


def salary_bands() -> list[dict]:
    """Bandas legacy (piso). Ver salary_options() para min/max."""
    from app.config import SMMLV_COP

    return [
        {"min_cop": SMMLV_COP, "label": f"1 SMMLV ({_cop_label(SMMLV_COP)})"},
        {"min_cop": 2_000_000, "label": f"Desde {_cop_label(2_000_000)}"},
        {"min_cop": 2_500_000, "label": f"Desde {_cop_label(2_500_000)}"},
        {"min_cop": 3_500_000, "label": f"Desde {_cop_label(3_500_000)}"},
    ]


def salary_options() -> dict:
    """Listas independientes para minimo y maximo.

    Minimo: desde 1 SMMLV hasta 9.5M. Maximo: 1M hasta 10M.
    Pasos de 500 mil.
    """
    from app.config import SMMLV_COP

    mins = [{"min_cop": SMMLV_COP,
             "label": f"1 SMMLV ({_cop_label(SMMLV_COP)})"}]
    mins += [{"min_cop": v, "label": f"Desde {_cop_label(v)}"}
             for v in range(2_000_000, 10_000_000, 500_000)]
    maxs = [{"max_cop": v, "label": f"Hasta {_cop_label(v)}"}
            for v in range(1_000_000, 10_500_000, 500_000)]
    return {"min_options": mins, "max_options": maxs}


def search_options() -> dict:
    """Catalogo para el frontend (una sola fuente de verdad)."""
    return {
        "seniority_levels": [
            {"id": i["id"], "label": i["label"]} for i in SENIORITY_LEVELS
        ],
        "experience_buckets": [
            {"years": i["years"], "label": i["label"]}
            for i in EXPERIENCE_BUCKETS
        ],
        "salary_bands": salary_bands(),
        "salary_min_options": salary_options()["min_options"],
        "salary_max_options": salary_options()["max_options"],
        "contract_types": CONTRACT_TYPES,
    }


def _clean_contracts(value) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    cleaned = [str(v).strip() for v in items if str(v or "").strip()]
    unknown = [v for v in cleaned if v not in CONTRACT_IDS]
    if unknown:
        raise ValueError(
            f"contract_types desconocidos: {', '.join(unknown)}.")
    return [v for v in CONTRACT_IDS_ORDER if v in cleaned]


CONTRACT_IDS_ORDER = ["obra_labor", "indefinido", "aprendizaje"]


def validate_fit_fields(data: dict) -> dict:
    """Valida las 4 variables (acepta None = heredar/sin filtro)."""
    data = dict(data or {})
    seniority = data.get("seniority")
    if seniority in (None, ""):
        seniority = None
    elif seniority not in SENIORITY_IDS:
        raise ValueError(
            f"seniority debe ser uno de: {', '.join(sorted(SENIORITY_IDS))}.")

    exp = data.get("experience_years")
    if exp in (None, ""):
        exp = None
    else:
        try:
            exp = float(exp)
        except (TypeError, ValueError):
            raise ValueError("experience_years debe ser numerico.")
        if exp not in EXPERIENCE_VALUES:
            raise ValueError(
                "experience_years debe ser una de las bandas "
                "(0.5, 1, 2, 3, 4, 5, +5).")

    salary = data.get("salary_min_cop")
    if salary in (None, ""):
        salary = None
    else:
        try:
            salary = int(salary)
        except (TypeError, ValueError):
            raise ValueError("salary_min_cop debe ser entero en COP.")
        if salary < 0:
            raise ValueError("salary_min_cop no puede ser negativo.")

    salary_max = data.get("salary_max_cop")
    if salary_max in (None, ""):
        salary_max = None
    else:
        try:
            salary_max = int(salary_max)
        except (TypeError, ValueError):
            raise ValueError("salary_max_cop debe ser entero en COP.")
        if salary_max < 0:
            raise ValueError("salary_max_cop no puede ser negativo.")

    if salary is not None and salary_max is not None \
            and salary > salary_max:
        raise ValueError(
            "salary_min_cop no puede superar a salary_max_cop.")

    contracts = data.get("contract_types")
    if contracts in (None, ""):
        contracts = []
    else:
        if isinstance(contracts, str):
            try:
                contracts = json.loads(contracts)
            except ValueError:
                contracts = [contracts]
        contracts = _clean_contracts(contracts)

    return {
        "seniority": seniority,
        "experience_years": exp,
        "salary_min_cop": salary,
        "salary_max_cop": salary_max,
        "contract_types": contracts,
    }


def _to_dict(uid: str, data: dict) -> dict:
    contracts = data.get("contract_types")
    if isinstance(contracts, str):
        try:
            contracts = json.loads(contracts)
        except ValueError:
            contracts = []
    return {
        "uid": uid,
        "seniority": data.get("seniority"),
        "experience_years": data.get("experience_years"),
        "salary_min_cop": data.get("salary_min_cop"),
        "salary_max_cop": data.get("salary_max_cop"),
        "contract_types": list(contracts or []),
    }


def get_search_config(db, uid: str) -> dict:
    """Global del usuario (todo None si nunca guardo = sin filtro)."""
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as fs

        current = fs.get_search_config(db, uid)
        if current is None:
            return {"uid": uid, "seniority": None,
                    "experience_years": None, "salary_min_cop": None,
                    "salary_max_cop": None, "contract_types": []}
        return _to_dict(uid, current)
    from app.database.models import SearchConfig

    row = db.query(SearchConfig).filter(SearchConfig.uid == uid).first()
    if row is None:
        return {"uid": uid, "seniority": None, "experience_years": None,
                "salary_min_cop": None, "salary_max_cop": None,
                "contract_types": []}
    return _to_dict(uid, {
        "seniority": row.seniority,
        "experience_years": row.experience_years,
        "salary_min_cop": row.salary_min_cop,
        "salary_max_cop": row.salary_max_cop,
        "contract_types": row.contract_types,
    })


def update_search_config(db, uid: str, fields: dict) -> dict:
    """PUT parcial: solo las claves enviadas cambian."""
    from app.database.firestore_client import is_firestore

    current = get_search_config(db, uid)
    merged = validate_fit_fields({**current, **(fields or {})})
    if is_firestore(db):
        from app.database import firestore_repo as fs

        saved = fs.save_search_config(db, uid, {
            **merged,
            "contract_types": json.dumps(merged["contract_types"]),
            "updated_at": datetime.utcnow(),
        })
        return _to_dict(uid, saved)
    from app.database.models import SearchConfig

    row = db.query(SearchConfig).filter(SearchConfig.uid == uid).first()
    if row is None:
        row = SearchConfig(uid=uid)
        db.add(row)
    row.seniority = merged["seniority"]
    row.experience_years = merged["experience_years"]
    row.salary_min_cop = merged["salary_min_cop"]
    row.salary_max_cop = merged["salary_max_cop"]
    row.contract_types = json.dumps(merged["contract_types"])
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _to_dict(uid, {
        "seniority": row.seniority,
        "experience_years": row.experience_years,
        "salary_min_cop": row.salary_min_cop,
        "salary_max_cop": row.salary_max_cop,
        "contract_types": row.contract_types,
    })


def resolve_fit_config(global_cfg: dict, profile: dict | None) -> dict:
    """Efectiva: cada variable del perfil si esta fijada, si no global.

    Devuelve siempre las 4 claves (None/[] = sin filtro en esa variable).
    """
    profile = profile or {}
    out = {
        "seniority": global_cfg.get("seniority"),
        "experience_years": global_cfg.get("experience_years"),
        "salary_min_cop": global_cfg.get("salary_min_cop"),
        "salary_max_cop": global_cfg.get("salary_max_cop"),
        "contract_types": list(global_cfg.get("contract_types") or []),
    }
    if profile.get("seniority"):
        out["seniority"] = profile["seniority"]
    if profile.get("experience_years") not in (None, ""):
        out["experience_years"] = profile["experience_years"]
    if profile.get("salary_min_cop") not in (None, ""):
        out["salary_min_cop"] = profile["salary_min_cop"]
    if profile.get("salary_max_cop") not in (None, ""):
        out["salary_max_cop"] = profile["salary_max_cop"]
    if profile.get("contract_types"):
        contracts = profile["contract_types"]
        if isinstance(contracts, str):
            try:
                contracts = json.loads(contracts)
            except ValueError:
                contracts = []
        if contracts:
            out["contract_types"] = list(contracts)
    return out


def resolve_for_request(db, uid: str | None,
                        profile: dict | None = None) -> dict:
    """Efectiva para un request: global del uid (o vacia) + perfil."""
    if not uid:
        return resolve_fit_config(
            {"seniority": None, "experience_years": None,
             "salary_min_cop": None, "salary_max_cop": None,
             "contract_types": []}, profile)
    return resolve_fit_config(get_search_config(db, uid), profile)
