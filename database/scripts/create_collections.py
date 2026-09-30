"""Crea la estructura base: documento _meta/schema con version.

Firestore crea colecciones al escribir el primer documento, asi que este
script deja un marcador de version (sirve para migraciones futuras).
Uso: python database/scripts/create_collections.py
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import get_client

SCHEMA_VERSION = "1.0.0"
COLLECTIONS = ["jobs", "applications", "cvs", "profiles", "interactions", "analytics"]


def main() -> None:
    db = get_client()
    db.collection("_meta").document("schema").set(
        {
            "version": SCHEMA_VERSION,
            "collections": COLLECTIONS,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
    )
    print(f"OK: _meta/schema v{SCHEMA_VERSION} ({', '.join(COLLECTIONS)})")


if __name__ == "__main__":
    main()
