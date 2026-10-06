"""Migracion a Firestore: helpers offline (sin credenciales).

Verifica conversion de fechas naive->UTC, parseo JSON y mapeo de
perfiles de busqueda con los campos fit. La parte que escribe en
Firestore se prueba contra prod con --dry-run.
"""
import importlib.util
from datetime import datetime
from pathlib import Path


def _load():
    path = (Path(__file__).resolve().parent.parent.parent
            / "database" / "scripts" / "migrate_sqlite_to_firestore.py")
    spec = importlib.util.spec_from_file_location("migrate_fs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aware_convierte_naive():
    migrate = _load()
    naive = datetime(2026, 1, 2, 3, 4, 5)
    aware = migrate._aware(naive)
    assert aware.tzinfo is not None
    assert (aware.year, aware.month, aware.day) == (2026, 1, 2)
    assert migrate._aware(None) is None
    assert migrate._aware("2026-01-01") == "2026-01-01"


def test_json_dict_tolerante():
    migrate = _load()
    assert migrate._json_dict('{"a": 1}') == {"a": 1}
    assert migrate._json_dict({"a": 1}) == {"a": 1}
    assert migrate._json_dict("no-json") == {}
    assert migrate._json_dict(None) == {}


def test_row_to_profile_dict_con_fit():
    from app.database.models import SearchProfile

    migrate = _load()
    row = SearchProfile(
        name="N", title="T", keywords='["a"]', sources='["computrabajo"]',
        active=1, frequency_minutes=10, max_age_days=0,
        seniority="junior", experience_years=2.0,
        salary_min_cop=2000000, salary_max_cop=3500000,
        contract_types='["indefinido"]',
    )
    data = migrate._row_to_profile_dict(row)
    assert data["seniority"] == "junior"
    assert data["experience_years"] == 2.0
    assert data["salary_min_cop"] == 2000000
    assert data["salary_max_cop"] == 3500000
    assert data["contract_types"] == ["indefinido"]
    assert data["keywords"] == ["a"]
    assert "id" not in data
