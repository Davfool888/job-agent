"""Valida la estructura SIN necesitar Firebase (offline).

Verifica:
1. schema/*.json son JSON validos con required/properties.
2. seed/sample_data.json valida contra esos esquemas (validador propio,
   subconjunto de JSON Schema: type, required, enum, minimum/maximum).
3. firestore.indexes.json parsea y solo referencia colecciones conocidas.
4. firestore.rules no contiene 'allow read, write: if true'.
5. seeds de jobs/applications/cvs/interactions cumplen enums cruzados
   (status validos, cv_id apunta a un cvs existente, job_id existe).
Uso: python database/scripts/validate_schema.py
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SCHEMA_DIR = BASE / "schema"
ERRORS: list[str] = []


def err(message: str) -> None:
    ERRORS.append(message)


def check_type(value, expected) -> bool:
    types = expected if isinstance(expected, list) else [expected]
    for t in types:
        if t == "string" and isinstance(value, str):
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "object" and isinstance(value, dict):
            return True
        if t == "null" and value is None:
            return True
    return False


def validate(doc: dict, schema: dict, path: str) -> None:
    if not isinstance(doc, dict):
        err(f"{path}: no es objeto")
        return
    for field in schema.get("required", []):
        if field not in doc:
            err(f"{path}: falta requerido '{field}'")
    props = schema.get("properties", {})
    for key, value in doc.items():
        if key == "id":
            continue
        spec = props.get(key)
        if spec is None:
            continue  # esquema flexible: permite campos futuros
        if "type" in spec and not check_type(value, spec["type"]):
            err(f"{path}.{key}: tipo invalido para {spec['type']}")
        if "enum" in spec and value not in spec["enum"]:
            err(f"{path}.{key}: '{value}' fuera de enum")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in spec and value < spec["minimum"]:
                err(f"{path}.{key}: menor que minimo")
            if "maximum" in spec and value > spec["maximum"]:
                err(f"{path}.{key}: mayor que maximo")
        if spec.get("type") == "array" and isinstance(value, list):
            item_type = (spec.get("items") or {}).get("type")
            for i, item in enumerate(value):
                if item_type and not check_type(item, item_type):
                    err(f"{path}.{key}[{i}]: tipo invalido")


def main() -> int:
    schemas = {}
    for name in ("jobs", "applications", "cvs", "profiles", "interactions", "analytics", "application_events", "search_profiles"):
        path = SCHEMA_DIR / f"{name}.json"
        if not path.exists():
            err(f"falta schema/{name}.json")
            continue
        try:
            schemas[name] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            err(f"schema/{name}.json invalido: {exc}")

    seed = json.loads((BASE / "seed" / "sample_data.json").read_text(encoding="utf-8"))
    mapping = {"jobs": "jobs", "applications": "applications", "cvs": "cvs",
               "profiles": "profiles", "interactions": "interactions"}
    for seed_key, schema_name in mapping.items():
        for i, doc in enumerate(seed.get(seed_key, [])):
            validate(doc, schemas[schema_name],
                     f"seed/{seed_key}[{i}]({doc.get('id', '?')})")
    for i, app in enumerate(seed.get("applications", [])):
        for j, event in enumerate(app.get("events", [])):
            validate(event, schemas["application_events"],
                     f"seed/applications[{i}].events[{j}]")

    # Referencias cruzadas.
    job_ids = {d.get("id") for d in seed.get("jobs", [])}
    cv_ids = {d.get("id") for d in seed.get("cvs", [])}
    for app in seed.get("applications", []):
        if app.get("job_id") not in job_ids:
            err(f"application {app.get('id')}: job_id inexistente")
        if app.get("cv_id") and app["cv_id"] not in cv_ids:
            err(f"application {app.get('id')}: cv_id inexistente")
    for cv in seed.get("cvs", []):
        if cv.get("job_id") not in job_ids:
            err(f"cv {cv.get('id')}: job_id inexistente")
    for inter in seed.get("interactions", []):
        if inter.get("job_id") and inter["job_id"] not in job_ids:
            err(f"interaction: job_id inexistente")

    # Indexes.
    try:
        indexes = json.loads((BASE / "firestore.indexes.json").read_text(encoding="utf-8"))
        known = {"jobs", "applications", "cvs", "profiles", "interactions", "analytics"}
        for idx in indexes.get("indexes", []):
            if idx.get("collectionGroup") not in known:
                err(f"indexes: coleccion desconocida {idx.get('collectionGroup')}")
    except ValueError as exc:
        err(f"firestore.indexes.json invalido: {exc}")

    # Rules: prohibido abierto.
    rules = (BASE / "firestore.rules").read_text(encoding="utf-8")
    if re.search(r"allow\s+read,\s*write\s*:\s*if\s+true", rules):
        err("firestore.rules deja acceso publico total (prohibido)")

    if ERRORS:
        print("FALLO validacion:")
        for message in ERRORS:
            print(f"  - {message}")
        return 1
    print("OK: esquemas, seed, indexes y rules consistentes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
