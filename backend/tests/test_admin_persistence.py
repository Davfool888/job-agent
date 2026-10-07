"""Persistencia del perfil ADMIN en modo Firestore.

Diagnostico: el perfil estructurado del admin se guardaba SOLO en
base_cv.json (disco efimero) aunque DB_BACKEND=firestore. Tras un
deploy (archivo perdido) el perfil volvia en blanco. Estos tests
exigen que quede en Firestore (profiles/base) y sobreviva.
"""
import pytest

ADMIN_UID = "uid-admin-test"
ADMIN_EMAIL = "davfool888@gmail.com"


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data else None


class _Doc:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self):
        return _Snap(self._store.get(self._key))

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            merged = {**self._store[self._key], **data}
        else:
            merged = dict(data)
        self._store[self._key] = merged


class _Col:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _Doc(self._store, str(key))


class FakeFirestoreDB:
    def __init__(self):
        self._cols = {}

    def collection(self, name):
        return _Col(self._cols.setdefault(name, {}))


@pytest.fixture()
def fsdb(monkeypatch, tmp_path):
    from app.database import firestore_client

    fake = FakeFirestoreDB()
    monkeypatch.setattr(firestore_client, "is_firestore",
                        lambda db: isinstance(db, FakeFirestoreDB))
    # Protege el base_cv.json real: el codigo viejo escribe al archivo.
    import app.config as config_module

    monkeypatch.setattr(config_module, "BASE_CV_PATH",
                        tmp_path / "base_cv.json")
    return fake


def test_admin_rich_se_persiste_en_firestore(fsdb):
    from app.services.job_service import save_rich_profile_for

    save_rich_profile_for(fsdb, ADMIN_UID, ADMIN_EMAIL, {
        "personal": {"full_name": "Admin Persistente",
                     "email": ADMIN_EMAIL},
        "professional_summary": "Resumen que debe sobrevivir.",
        "experience": [{"title": "Dev", "company": "Acme",
                        "description": "Datos propios."}],
    })
    base = fsdb._cols.get("profiles", {}).get("base")
    assert base is not None, \
        "profiles/base no existe: el perfil admin NO se guardo en Firestore"


def test_admin_rich_sobrevive_deploy(fsdb, tmp_path):
    """Simula deploy: el archivo local desaparece, Firestore queda."""
    from app.services.job_service import (
        get_rich_profile_for, save_rich_profile_for)

    save_rich_profile_for(fsdb, ADMIN_UID, ADMIN_EMAIL, {
        "personal": {"full_name": "Admin Persistente",
                     "email": ADMIN_EMAIL},
        "professional_summary": "Resumen que debe sobrevivir.",
    })
    # Deploy: disco efimero perdido (ni siquiera existe el archivo).
    import app.config as config_module

    assert not config_module.BASE_CV_PATH.exists()
    rich = get_rich_profile_for(fsdb, ADMIN_UID, ADMIN_EMAIL)
    assert rich["personal"]["full_name"] == "Admin Persistente"
    assert "sobrevivir" in rich["professional_summary"]


def test_google_rich_sigue_aislado(fsdb):
    from app.services.job_service import (
        get_rich_profile_for, save_rich_profile_for)

    save_rich_profile_for(fsdb, "uid-google", "g@test.test", {
        "personal": {"full_name": "Usuario Google",
                     "email": "g@test.test"},
    })
    mine = get_rich_profile_for(fsdb, "uid-google", "g@test.test")
    assert mine["personal"]["full_name"] == "Usuario Google"
    assert mine["scope"] == "own"
