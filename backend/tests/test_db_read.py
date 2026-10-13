"""db_read: los fallos de BD salen como HTTPException (con CORS)."""
import pytest
from fastapi import HTTPException

from app.routers.common import db_read


class _QuotaError(Exception):
    pass


def test_passthrough_ok_y_httpexception():
    assert db_read(lambda: {"a": 1}) == {"a": 1}
    with pytest.raises(HTTPException) as exc:
        db_read(_boom_404)
    assert exc.value.status_code == 404


def _boom_404():
    raise HTTPException(status_code=404, detail="No.")


def test_quota_429_mapea_503():
    with pytest.raises(HTTPException) as exc:
        db_read(_boom_quota)
    assert exc.value.status_code == 503
    assert "429" in exc.value.detail or "cuota" in exc.value.detail


def _boom_quota():
    raise _QuotaError("429 Quota exceeded.")


def test_otro_fallo_mapea_502():
    with pytest.raises(HTTPException) as exc:
        db_read(_boom_otro)
    assert exc.value.status_code == 502


def _boom_otro():
    raise RuntimeError("grpc roto")
