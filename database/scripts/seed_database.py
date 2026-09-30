"""Carga database/seed/sample_data.json a Firestore.

Convierte strings ISO en *_at/date/timestamp a datetime. Los eventos de
cada application van a la subcoleccion events/.
Uso: python database/scripts/seed_database.py [--file ruta.json]
"""
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import get_client

SEED_PATH = Path(__file__).resolve().parent.parent / "seed" / "sample_data.json"


def to_datetime(value):
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def convert_times(doc: dict) -> dict:
    out = {}
    for key, value in doc.items():
        if key == "events":
            continue
        if isinstance(value, dict):
            value = convert_times(value)
        elif isinstance(value, list):
            value = [convert_times(v) if isinstance(v, dict) else v for v in value]
        if key == "timestamp" or key.endswith("_at") or key == "date":
            value = to_datetime(value)
        out[key] = value
    return out


def main(path: str = str(SEED_PATH)) -> None:
    db = get_client()
    seed = json.loads(Path(path).read_text(encoding="utf-8"))
    counts = {}
    for collection in ("jobs", "cvs", "profiles", "interactions"):
        counts[collection] = 0
        for doc in seed.get(collection, []):
            doc_id = doc.pop("id", None)
            ref = db.collection(collection).document(doc_id) if doc_id else db.collection(collection).document()
            ref.set(convert_times(doc))
            counts[collection] += 1
    counts["applications"] = 0
    counts["events"] = 0
    for app in seed.get("applications", []):
        events = app.pop("events", [])
        app_id = app.pop("id", None)
        ref = db.collection("applications").document(app_id) if app_id else db.collection("applications").document()
        ref.set(convert_times(app))
        counts["applications"] += 1
        for event in events:
            ref.collection("events").add(convert_times(event))
            counts["events"] += 1
    print("OK seed:", ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(SEED_PATH))
