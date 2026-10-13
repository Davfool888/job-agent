"""Backfill resiliente: la cuota agotada (429) no tumba el arranque."""


class _QuotaError(Exception):
    pass


def test_backfill_429_no_tumba(monkeypatch):
    """Firestore con cuota excedida: devuelve 0 en vez de lanzar."""
    from app.services import job_service as jobs

    monkeypatch.setattr(jobs, "is_firestore", lambda db: True)
    import app.database.firestore_repo as fs_repo

    def _boom(db):
        raise _QuotaError("429 Quota exceeded.")

    monkeypatch.setattr(fs_repo, "iter_all_jobs", _boom)
    assert jobs.backfill_fingerprints(object()) == 0


def test_skip_backfill_flag(monkeypatch):
    """SKIP_BACKFILL=true: no toca la BD y devuelve 0."""
    from app.services import job_service as jobs

    monkeypatch.setenv("SKIP_BACKFILL", "true")
    # object() como db: cualquier acceso real explotaria.
    assert jobs.backfill_fingerprints(object()) == 0
