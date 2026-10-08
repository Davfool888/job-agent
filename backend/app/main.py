"""App FastAPI (Fase 1: factory delgado; endpoints en app/routers/*).

Orden de inclusion preservado: system, auth, profiles,
search_profiles, discovery (con /jobs/search y /search/stream)
y jobs (con /jobs/{job_id}) al final para no capturar /search.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_NAME
from app.config import FRONTEND_ORIGINS
from app.database.connection import Base
from app.database.connection import SessionLocal
from app.database.connection import engine
from app.database.connection import ensure_columns
from app.database.models import Job  # noqa: F401
from app.database.models import PDFConfig  # noqa: F401
from app.database.models import Profile  # noqa: F401
from app.database.models import ProfileCV  # noqa: F401
from app.database.models import SearchConfig  # noqa: F401
from app.database.models import SearchProfile  # noqa: F401
from app.database.models import User  # noqa: F401
from app.database.models import UserProfile  # noqa: F401
from app.database.models import UserRichProfile  # noqa: F401
from app.routers import auth as auth_router
from app.routers import ai_keys as ai_keys_router
from app.routers import discovery as discovery_router
from app.routers import jobs as jobs_router
from app.routers import profiles as profiles_router
from app.routers import search_profiles as search_profiles_router
from app.routers import system as system_router
from app.routers import telegram as telegram_router
# Re-export para compatibilidad con tests que parchan app.main.get_scraper
from app.scraper.registry import available_sources  # noqa: F401
from app.scraper.registry import get_scraper  # noqa: F401
from app.services.job_service import backfill_fingerprints


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging as _logging
    import os as _os

    from app.config import DB_BACKEND, FIREBASE_PROJECT_ID

    _log = _logging.getLogger("job-agent.lifespan")
    if DB_BACKEND == "firestore":
        from app.database.firestore_client import FirestoreDatabase

        try:
            db = FirestoreDatabase()
        except Exception as error:
            # Fallar rapido y en voz alta: arrancar sin BD real
            # significaria perder datos sin que nadie lo note.
            raise RuntimeError(
                "DB_BACKEND=firestore pero sin credenciales validas. "
                "Define FIREBASE_SERVICE_ACCOUNT_B64 (recomendado en "
                "Render) o FIREBASE_SERVICE_ACCOUNT_JSON o "
                "GOOGLE_APPLICATION_CREDENTIALS. Error original: "
                f"{error}"
            ) from error
        _log.warning("DB backend: firestore (proyecto %s, persistente).",
                     FIREBASE_PROJECT_ID or "?")
        backfill_fingerprints(db)
    else:
        if not _os.getenv("ALLOW_EPHEMERAL_SQLITE"):
            _log.warning(
                "DB backend: sqlite LOCAL (efimero en Render sin disco: "
                "los datos SE PIERDEN en cada deploy/reinicio). Para "
                "produccion usa DB_BACKEND=firestore.")
        Base.metadata.create_all(bind=engine)
        ensure_columns()
        db = SessionLocal()
        try:
            backfill_fingerprints(db)
        finally:
            db.close()
    import sys as _sys

    under_test = (
        "PYTEST_CURRENT_TEST" in _os.environ
        or "pytest" in (_sys.argv[0] if _sys.argv else "")
    )
    if not under_test:
        from app.scheduler import start_scheduler

        start_scheduler()
        try:
            from app.adapt.pdf import warmup_chromium

            warmup_chromium()
        except Exception:  # noqa: BLE001
            pass
        # Webhook de Telegram (best-effort, nunca tumba el arranque).
        # Solo el bot global legacy: los bots propios registran el suyo
        # al guardar la key (POST /telegram/bot).
        try:
            from app.config import TELEGRAM_PUBLIC_URL
            from app.services import telegram as _tg

            base = (TELEGRAM_PUBLIC_URL or "").strip().rstrip("/")
            if base and _tg._global_token():
                from app.config import TELEGRAM_WEBHOOK_SECRET

                payload = {"url": f"{base}/telegram/webhook"}
                if (TELEGRAM_WEBHOOK_SECRET or "").strip():
                    payload["secret_token"] = \
                        TELEGRAM_WEBHOOK_SECRET.strip()
                _tg._api("setWebhook", payload, _tg._global_token(),
                         timeout=15)
                _log.warning("Telegram webhook registrado: %s",
                             payload["url"])
        except Exception as error:  # noqa: BLE001
            _log.warning("Telegram webhook no registrado: %s", error)
    yield
    from app.scheduler import stop_scheduler

    stop_scheduler()


app = FastAPI(title=APP_NAME, version="0.5.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def collapse_slashes(request: Request, call_next):
    """Colapsa // intermedios del path (clientes que concatenan
    API_URL con slash final + "/ruta"). FastAPI no lo hace solo y
    devuelve 404 generico."""
    import re

    path = request.scope.get("path", "")
    collapsed = re.sub(r"/{2,}", "/", path)
    if collapsed != path:
        request.scope["path"] = collapsed
    return await call_next(request)


app.include_router(system_router.router)
app.include_router(auth_router.router)
app.include_router(ai_keys_router.router)
app.include_router(profiles_router.router)
app.include_router(search_profiles_router.router)
app.include_router(telegram_router.router)
app.include_router(discovery_router.router)
app.include_router(jobs_router.router)
