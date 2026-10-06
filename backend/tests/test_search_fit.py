"""Filtros de ajuste (fit): titulo+descripcion, jerarquia perfil>global.

Reglas: solo descarta ante contradiccion explicita; sin dato la
oferta pasa a la siguiente variable. Sin config no filtra nada.
"""
from fastapi.testclient import TestClient

from app.analysis import fit
from app.main import app

SMMLV = 1_423_500


def _job(title, description="", salary=""):
    return {"title": title, "description": description, "salary": salary}


def test_seniority_solo_descarta_nivel_superior():
    assert fit.detect_seniority("Desarrollador Senior Java") == "senior"
    assert fit.detect_seniority("Analista semi-senior BI") == "mid"
    assert fit.detect_seniority("Auxiliar junior contable") == "junior"
    assert fit.detect_seniority("Practicante universitario") == "trainee"
    assert fit.detect_seniority("Analista de datos Power BI") is None

    cfg = {"seniority": "junior"}
    assert fit.check_job(_job("Dev Senior"), cfg, SMMLV)[0] is False
    assert fit.check_job(_job("Dev Junior"), cfg, SMMLV)[0] is True
    # Sin dato en la oferta: pasa (continua a la siguiente variable).
    assert fit.check_job(_job("Analista de datos"), cfg, SMMLV)[0] is True
    # Senior configurado: ve hasta su nivel.
    senior = {"seniority": "senior"}
    assert fit.check_job(_job("Dev Junior"), senior, SMMLV)[0] is True


def test_experiencia_titulo_y_descripcion():
    assert fit.parse_experience_required(
        "Se requieren 3 años de experiencia.") == 3.0
    assert fit.parse_experience_required(
        "Mínimo 2 años en ventas") == 2.0
    assert fit.parse_experience_required("Sin experiencia previa") == 0.0
    assert fit.parse_experience_required("6 meses de experiencia") == 0.5
    assert fit.parse_experience_required("Buscamos analista.") is None

    cfg = {"experience_years": 2.0}
    assert fit.check_job(
        _job("Dev", "Piden 5 años de experiencia."), cfg, SMMLV)[0] is False
    assert fit.check_job(
        _job("Dev", "Con 1 año de experiencia basta."), cfg, SMMLV)[0] is True
    assert fit.check_job(_job("Dev", "Sin requisitos."), cfg, SMMLV)[0] is True


def test_salario_rangos_y_smmlv():
    assert fit.parse_salary_range("$3.500.000", SMMLV) == (3500000.0, 3500000.0)
    assert fit.parse_salary_range("$2 a $3 millones", SMMLV) == (
        2000000.0, 3000000.0)
    assert fit.parse_salary_range("2 SMMLV", SMMLV) == (
        float(2 * SMMLV), float(2 * SMMLV))
    assert fit.parse_salary_range("Salario: 1 SMMLV", SMMLV) == (
        float(SMMLV), float(SMMLV))
    assert fit.parse_salary_range("USD 2000 monthly", SMMLV) is None
    assert fit.parse_salary_range("A convenir", SMMLV) is None

    cfg = {"salary_min_cop": 3_500_000}
    assert fit.check_job(
        _job("Dev", "", "$2.000.000"), cfg, SMMLV)[0] is False
    assert fit.check_job(
        _job("Dev", "", "$3.000.000 a $4.000.000"), cfg, SMMLV)[0] is True
    assert fit.check_job(_job("Dev", "Salario a convenir"), cfg, SMMLV)[0] is True


def test_contrato_solo_mencion_explicita():
    assert fit.detect_contracts("Contrato a término indefinido") == {"indefinido"}
    assert fit.detect_contracts("Obra o labor determinada") == {"obra_labor"}
    assert fit.detect_contracts("Contrato de aprendizaje SENA") == {"aprendizaje"}
    assert fit.detect_contracts("Tiempo completo, híbrido") == set()

    cfg = {"contract_types": ["indefinido"]}
    assert fit.check_job(
        _job("Dev", "Contrato a término fijo."), cfg, SMMLV)[0] is False
    assert fit.check_job(
        _job("Dev", "Término indefinido."), cfg, SMMLV)[0] is True
    assert fit.check_job(_job("Dev", "Tiempo completo."), cfg, SMMLV)[0] is True


def test_apply_fit_sin_config_no_filtra():
    jobs = [_job("Dev Senior", "$1.000.000", )]
    kept, discarded = fit.apply_fit(jobs, {}, SMMLV)
    assert kept == jobs and discarded == {}
    kept, _ = fit.apply_fit(
        jobs, {"seniority": None, "experience_years": None,
               "salary_min_cop": None, "contract_types": []}, SMMLV)
    assert len(kept) == 1


def test_jerarquia_perfil_sobre_global():
    from app.services.search_config import resolve_fit_config

    global_cfg = {"seniority": "senior", "experience_years": 5.0,
                  "salary_min_cop": 2_000_000,
                  "contract_types": ["indefinido"]}
    assert resolve_fit_config(global_cfg, None)["seniority"] == "senior"
    out = resolve_fit_config(global_cfg, {"seniority": "junior"})
    assert out["seniority"] == "junior"  # perfil gana
    assert out["experience_years"] == 5.0  # resto hereda
    out = resolve_fit_config(global_cfg, {"contract_types": []})
    assert out["contract_types"] == ["indefinido"]  # vacio = hereda


def test_search_config_endpoints():
    import app.auth as auth_module

    orig = auth_module.verify_bearer_token
    auth_module.verify_bearer_token = lambda h: {
        "uid": "uid-fit-test", "email": "fit@test.test", "name": "F"}
    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer x"}
            assert client.get(
                "/search-config/options").status_code == 200
            empty = client.get("/search-config", headers=headers).json()
            assert empty["seniority"] is None
            bad = client.put("/search-config", json={"seniority": "dios"},
                             headers=headers)
            assert bad.status_code == 400
            ok = client.put("/search-config", json={
                "seniority": "junior", "experience_years": 2,
                "salary_min_cop": 2000000,
                "contract_types": ["indefinido"],
            }, headers=headers)
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert body["seniority"] == "junior"
            assert body["experience_years"] == 2.0
            # PUT parcial conserva lo demas.
            again = client.put("/search-config", json={"seniority": "mid"},
                               headers=headers).json()
            assert again["seniority"] == "mid"
            assert again["salary_min_cop"] == 2000000
    finally:
        auth_module.verify_bearer_token = orig
        from app.database.connection import SessionLocal
        from app.database.models import SearchConfig

        db = SessionLocal()
        try:
            db.query(SearchConfig).filter(
                SearchConfig.uid == "uid-fit-test").delete(
                    synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_perfil_crud_con_fit():
    with TestClient(app) as client:
        created = client.post("/search-profiles", json={
            "name": "FitTest", "title": "Analista",
            "sources": ["computrabajo"], "seniority": "junior",
            "experience_years": 1, "salary_min_cop": 2500000,
            "contract_types": ["aprendizaje"],
        })
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        try:
            body = created.json()
            assert body["seniority"] == "junior"
            assert body["contract_types"] == ["aprendizaje"]
            bad = client.post("/search-profiles", json={
                "name": "FitTest2", "title": "X",
                "sources": ["computrabajo"], "seniority": "emperador"})
            assert bad.status_code == 400
        finally:
            client.delete(f"/search-profiles/{pid}")
