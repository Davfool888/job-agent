"""Colision naive/aware con Firestore (solo falla en prod).

Firestore devuelve timestamps CON zona (+00:00); el codigo comparaba
con datetime.utcnow() naive -> TypeError y 500 silenciosos (el
scheduler ni corria, el link de Telegram nunca confirmaba, y
"nuevas" siempre era 0). Estos tests usan timestamps aware, la forma
exacta de produccion.
"""
from datetime import datetime, timedelta, timezone


def test_as_naive_utc():
    from app.database.firestore_client import as_naive_utc

    assert as_naive_utc(None) is None
    assert as_naive_utc("") is None
    assert as_naive_utc("basura") is None
    naive = datetime(2026, 10, 7, 12, 0, 0)
    assert as_naive_utc(naive) == naive
    aware = datetime(2026, 10, 7, 14, 0, 0,
                     tzinfo=timezone(timedelta(hours=2)))
    assert as_naive_utc(aware) == datetime(2026, 10, 7, 12, 0, 0)
    assert as_naive_utc("2026-10-07T12:00:00+00:00") == naive
    assert as_naive_utc("2026-10-07T12:00:00Z") == naive
    assert as_naive_utc("2026-10-07 12:00:00") == naive


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data else None


class _Doc:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self):
        return _Snap(self._key, self._store.get(self._key))

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            merged = {**self._store[self._key], **data}
        else:
            merged = dict(data)
        self._store[self._key] = merged


class _Query:
    def __init__(self, store, field, value):
        self._store = store
        self._field = field
        self._value = value

    def stream(self):
        for key, data in self._store.items():
            if isinstance(data, dict) and data.get(self._field) == self._value:
                yield _Snap(key, data)


class _Col:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _Doc(self._store, str(key))

    def where(self, field, op, value):
        assert op == "=="
        return _Query(self._store, field, value)


class FakeFirestoreDB:
    def __init__(self):
        self._cols = {}

    def collection(self, name):
        return _Col(self._cols.setdefault(name, {}))


def _firestore(monkeypatch):
    from app.database import firestore_client

    fake = FakeFirestoreDB()
    monkeypatch.setattr(firestore_client, "is_firestore",
                        lambda db: isinstance(db, FakeFirestoreDB))
    return fake


def test_confirm_link_con_timestamp_aware(monkeypatch):
    """Forma exacta de prod: si revienta aqui, en prod da 500."""
    from app.services import telegram as tg

    fake = _firestore(monkeypatch)
    aware_now = datetime.now(timezone.utc)
    fake._cols.setdefault("telegram_links", {})["u1"] = {
        "link_code": "ABC123xyz",
        "code_created_at": aware_now,
        "code_used": 0,
    }
    result = tg.confirm_link(fake, "ABC123xyz", 777, "tester")
    assert result == {"uid": "u1"}
    assert fake._cols["telegram_links"]["u1"]["chat_id"] == "777"


def test_confirm_link_expirado_aware(monkeypatch):
    from app.services import telegram as tg

    fake = _firestore(monkeypatch)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    fake._cols.setdefault("telegram_links", {})["u1"] = {
        "link_code": "VIEJO123",
        "code_created_at": old,
        "code_used": 0,
    }
    try:
        tg.confirm_link(fake, "VIEJO123", 777, None)
        raise AssertionError("debió expirar")
    except tg.TelegramError as error:
        assert error.code == "expired"


def test_profile_lock_con_timestamp_aware():
    from app.scheduler import _profile_is_locked

    now = datetime.utcnow()
    recent = {"id": "1", "last_run_status": "running",
              "last_run_at": datetime.now(timezone.utc)}
    assert _profile_is_locked(recent, now) is True
    old = {"id": "1", "last_run_status": "running",
           "last_run_at": datetime.now(timezone.utc) - timedelta(hours=2)}
    assert _profile_is_locked(old, now) is False
    assert _profile_is_locked({"id": "1"}, now) is False


def test_due_check_con_timestamp_aware():
    """Replica la comparacion de run_due_profiles con dato de prod."""
    from app.database.firestore_client import as_naive_utc

    now = datetime.utcnow()
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert as_naive_utc(future) > now
    assert not as_naive_utc(past) > now
