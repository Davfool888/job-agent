"""Visibilidad del catalogo de ofertas: global, decisiones por usuario.

Bug: una oferta guardada por otra identidad (scheduler, invitado o
sin sesion) devolvia 404 al abrirla con sesion distinta, aunque el
listado/buscador la mostraba. Las ofertas son catalogo global con
dedup; lo per-usuario es el ESTADO (vista/guardada/descartada).
"""
from fastapi.testclient import TestClient

from app.main import app

COMPANY = "Empresa Visibilidad Test"
UID_A = "uid-vis-a"
EMAIL_A = "a@test.test"
UID_B = "uid-vis-b"
EMAIL_B = "b@test.test"


def _db():
    from app.database.connection import SessionLocal

    return SessionLocal()


def _clean():
    from app.database.models import Job, UserJobState

    db = _db()
    try:
        db.query(Job).filter(Job.company == COMPANY).delete(
            synchronize_session=False)
        try:
            db.query(UserJobState).filter(
                UserJobState.company == COMPANY).delete(
                    synchronize_session=False)
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    finally:
        db.close()


def _save_as(owner_uid, owner_email):
    from app.services.job_service import save_jobs

    db = _db()
    try:
        saved = save_jobs(db, [{
            "title": "Analista Visibilidad", "company": COMPANY,
            "url": "https://example.com/vis-1",
            "description": "Python SQL datos " * 20,
            "source": "computrabajo",
        }], search_query="visibilidad", uid=owner_uid, email=owner_email)
        return saved[0].id
    finally:
        db.close()


def _auth(uid, email):
    import app.auth as auth_module

    def fake_verify(authorization):
        assert (authorization or "").startswith("Bearer ")
        return {"uid": uid, "email": email, "name": "T"}

    return auth_module, fake_verify


def test_otro_usuario_abre_oferta_ajena():
    import app.auth as auth_module

    _clean()
    job_id = _save_as(UID_A, EMAIL_A)
    orig = auth_module.verify_bearer_token
    auth_module.verify_bearer_token = lambda h: {
        "uid": UID_B, "email": EMAIL_B, "name": "B"}
    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer x"}
            r = client.get(f"/jobs/{job_id}", headers=headers)
            assert r.status_code == 200, r.text
            listed = client.get("/jobs", params={"limit": 500},
                                headers=headers).json()
            assert job_id in {j["id"] for j in listed}
    finally:
        auth_module.verify_bearer_token = orig
        _clean()


def test_oferta_sin_dueno_abre_con_sesion():
    import app.auth as auth_module

    _clean()
    job_id = _save_as(None, None)
    orig = auth_module.verify_bearer_token
    auth_module.verify_bearer_token = lambda h: {
        "uid": UID_B, "email": EMAIL_B, "name": "B"}
    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer x"}
            r = client.get(f"/jobs/{job_id}", headers=headers)
            assert r.status_code == 200, r.text
    finally:
        auth_module.verify_bearer_token = orig
        _clean()


def test_estado_global_compartido():
    """El ESTADO hoy es global (un discard lo ven todos); lo que se
    volvio universal es la VISIBILIDAD. Si algun dia se cablean los
    estados por usuario (save_user_job_state existe pero sin uso),
    este test debera cambiar a per-usuario."""
    import app.auth as auth_module

    _clean()
    job_id = _save_as(UID_A, EMAIL_A)
    orig = auth_module.verify_bearer_token

    def _as(uid, email):
        auth_module.verify_bearer_token = lambda h: {
            "uid": uid, "email": email, "name": "T"}

    try:
        with TestClient(app) as client:
            _as(UID_B, EMAIL_B)
            headers_b = {"Authorization": "Bearer x"}
            assert client.patch(
                f"/jobs/{job_id}/status", json={"status": "discarded"},
                headers=headers_b).status_code == 200
            assert client.get(
                f"/jobs/{job_id}",
                headers=headers_b).json()["status"] == "discarded"
            _as(UID_A, EMAIL_A)
            headers_a = {"Authorization": "Bearer x"}
            assert client.get(
                f"/jobs/{job_id}",
                headers=headers_a).json()["status"] == "discarded"
    finally:
        auth_module.verify_bearer_token = orig
        _clean()


def test_id_inexistente_sigue_404():
    with TestClient(app) as client:
        assert client.get("/jobs/999999999").status_code == 404
