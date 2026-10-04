"""Fase 2: pdf-config funciona igual en SQLite y Firestore.

Firestore real no disponible en este entorno (cygrpc bloqueado),
asi que se usa un stub de FirestoreDatabase con la misma API
(collection().document().get()/set()/delete()) para probar la
rama is_firestore del servicio sin red.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


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

    def delete(self):
        self._store.pop(self._key, None)


class _Col:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _Doc(self._store, str(key))


class FakeFirestoreDB:
    """Misma forma que FirestoreDatabase para is_firestore()."""

    def __init__(self):
        self._cols = {}

    def collection(self, name):
        return _Col(self._cols.setdefault(name, {}))


@pytest.fixture()
def _as_firestore(monkeypatch):
    from app.database import firestore_client

    fake = FakeFirestoreDB()
    monkeypatch.setattr(firestore_client, "FirestoreDatabase",
                        lambda: fake)
    monkeypatch.setattr(firestore_client, "is_firestore",
                        lambda db: isinstance(db, FakeFirestoreDB))
    return fake


@pytest.fixture()
def _auth(monkeypatch):
    import app.auth as auth_module

    def fake_verify(authorization):
        assert (authorization or "").startswith("Bearer ")
        return {"uid": "uid-fase2", "email": "fase2@test.test",
                "name": "F2"}

    monkeypatch.setattr(auth_module, "verify_bearer_token", fake_verify)
    yield
    from app.database.connection import SessionLocal
    from app.database.models import PDFConfig

    db = SessionLocal()
    try:
        db.query(PDFConfig).filter(
            PDFConfig.uid == "uid-fase2").delete(
                synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _headers():
    return {"Authorization": "Bearer x"}


def test_sqlite_crud_y_validacion(_auth):
    # Contrato SQLite intacto tras Fase 2.
    with TestClient(app) as client:
        assert client.get("/pdf-config",
                          headers=_headers()).status_code == 200
        bad = client.put("/pdf-config", json={"font_size_pt": 13},
                         headers=_headers())
        assert bad.status_code == 400
        ok = client.put("/pdf-config", json={"font_size_pt": 14},
                        headers=_headers())
        assert ok.status_code == 200
        assert ok.json()["font_size_pt"] == 14
        body = client.put("/pdf-config", json={
            "margin_top_mm": 10, "accent_color": "#ff0000",
        }, headers=_headers()).json()
        assert body["margin_top_mm"] == 25
        assert body["accent_color"] == "#000000"
        reset = client.post("/pdf-config/reset",
                            headers=_headers()).json()
        assert reset["font_size_pt"] == 11


def test_firestore_rama_servicio(_as_firestore):
    from app.services import pdf_config as svc

    db = _as_firestore
    got = svc.get_pdf_config(db, "u1")
    assert got["font_size_pt"] == 11
    assert got["margin_top_mm"] == 25
    updated = svc.update_pdf_config(db, "u1", {"font_size_pt": 14})
    assert updated["font_size_pt"] == 14
    # APA forzado tambien en Firestore.
    forced = svc.update_pdf_config(
        db, "u1", {"margin_top_mm": 10, "accent_color": "#ff0000"})
    assert forced["margin_top_mm"] == 25
    assert forced["accent_color"] == "#000000"
    with pytest.raises(ValueError):
        svc.update_pdf_config(db, "u1", {"font_size_pt": 13})
    reset = svc.reset_pdf_config(db, "u1")
    assert reset["font_size_pt"] == 11
    # Renderer recibe dict listo, sin ORM.
    render = svc.get_pdf_config_for_renderer(db, "u1")
    assert isinstance(render["section_order"], list)
    assert render["font_size_pt"] == 11
    assert svc.get_pdf_config_for_renderer(db, None) == {}


def test_adapt_usa_servicio_sin_sql_directo(_auth):
    # adapt/service.py ya no hace db.query(PDFConfig): si la tabla
    # volara, igual genera con defaults en vez de 500.
    from app.services import pdf_config as svc

    assert "db.query" not in open(
        "app/adapt/service.py", encoding="utf-8").read().split(
        "def adapt_profile_for_job")[1].split("def error_body")[0]
    assert callable(svc.get_pdf_config_for_renderer)
