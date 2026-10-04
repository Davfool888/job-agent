"""Fase 1: split app/main.py en routers sin cambiar lógica.

Uso: python scripts/_fase1_split.py
- Extrae cada endpoint con sus decoradores verbatim, cambia @app. -> @router.
- Reescribe get_scraper(/available_sources( bare -> registry.get_scraper(
  para que los tests parcheen app.scraper.registry (como ya hace test_scheduler).
- Genera app/routers/{common,system,auth,profiles,search_profiles,discovery,jobs}.py
- Reescribe app/main.py como factory delgado que incluye routers en orden.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"
ROUTERS = ROOT / "app" / "routers"

COMMON_FUNCS = {
    "_json_list", "_auth_account_complete", "_pdf_config_to_out",
    "_profile_identity", "_adapt_identity",
}
COMMON_CLASSES = {"PDFConfigOut", "PDFConfigIn"}

GROUPS = {
    "system": {"root", "health", "health_detailed", "stats", "analytics",
               "ai_status", "list_sources"},
    "auth": {"auth_status", "auth_me", "auth_update_me",
             "auth_register", "auth_login"},
    "profiles": {"get_pdf_config", "update_pdf_config", "reset_pdf_config",
                 "read_profile", "write_profile", "read_catalogs",
                 "read_full_profile", "write_full_profile",
                 "import_latex_profile"},
    "search_profiles": {"list_search_profiles", "create_search_profile",
                        "get_search_profile", "update_search_profile",
                        "delete_search_profile", "run_search_profile_now",
                        "upload_search_profile_cv", "get_search_profile_cv",
                        "download_search_profile_cv",
                        "delete_search_profile_cv", "scheduler_status",
                        "scheduler_tick"},
    "discovery": {"discovery_packs", "discover_jobs",
                  "analyze_pending_endpoint", "search_jobs",
                  "search_jobs_stream"},
    # resto -> jobs
}

ORDER = ["system", "auth", "profiles", "search_profiles", "discovery", "jobs"]

HEADER = '''"""Router {name} (Fase 1: extraido de app/main.py sin cambios de logica)."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import APP_NAME
from app.database.connection import get_db
from app.database.models import JOB_STATUSES
from app.database.models import Job  # noqa: F401
from app.database.models import PDFConfig  # noqa: F401
from app.database.models import Profile  # noqa: F401
from app.database.models import ProfileCV  # noqa: F401
from app.database.models import User  # noqa: F401
from app.database.models import UserProfile  # noqa: F401
from app.database.models import UserRichProfile  # noqa: F401
from app.schemas.job import JobResponse
from app.schemas.job import JobStatusUpdate
from app.scraper import registry
from app.services.job_service import analyze_pending
from app.services.job_service import get_all_jobs
from app.services.job_service import get_job_by_id
from app.services.job_service import get_profile
from app.services.job_service import get_profile_for
from app.services.job_service import get_stats
from app.services.job_service import save_analysis
from app.services.job_service import save_jobs
from app.services.job_service import save_profile
from app.services.job_service import update_job_status
from .common import _adapt_identity
from .common import _auth_account_complete
from .common import _json_list
from .common import _pdf_config_to_out
from .common import _profile_identity
from .common import PDFConfigIn
from .common import PDFConfigOut

router = APIRouter()
'''

COMMON_HEADER = '''"""Helpers compartidos (Fase 1: movidos de app/main.py sin cambios)."""
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel

from app.database.models import PDFConfig


def _json_list(value) -> list:
'''


def main():
    src = MAIN.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)

    # nombre -> (start_line(1-based, primer decorador), end_line)
    spans = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
            start = node.lineno
            if node.decorator_list:
                start = min(d.lineno for d in node.decorator_list)
            # incluir comentarios inmediatamente anteriores tipo "# ===" ?
            spans[node.name] = (start, node.end_lineno)

    # clasificar
    buckets = {k: [] for k in ORDER}
    commons = []
    for name, (s, e) in spans.items():
        if name in COMMON_FUNCS or name in COMMON_CLASSES:
            commons.append((s, name))
        else:
            placed = False
            for g, names in GROUPS.items():
                if name in names:
                    buckets[g].append((s, name))
                    placed = True
                    break
            if not placed and name not in (
                    "lifespan", "collapse_slashes"):
                # todo lo demas con decorador @app. va a jobs
                buckets["jobs"].append((s, name))

    ROUTERS.mkdir(exist_ok=True)
    (ROUTERS / "__init__.py").write_text(
        '"""Routers FastAPI (Fase 1). Orden: system, auth, profiles, '
        'search_profiles, discovery, jobs."""\n', encoding="utf-8")

    # common.py: extraer verbatim los helpers + clases
    commons.sort()
    common_parts = [COMMON_HEADER]
    for s, name in commons:
        e = spans[name][1]
        seg = "".join(lines[s - 1:e])
        # quitar el def _json_list duplicado del header
        if name == "_json_list":
            # seg incluye "def _json_list..." completo; el header ya
            # aporta la firma, asi que tomamos solo el cuerpo
            body_lines = seg.splitlines(keepends=True)[1:]
            common_parts.append("".join(body_lines))
        else:
            common_parts.append(seg)
        common_parts.append("\n\n")
    (ROUTERS / "common.py").write_text(
        "".join(common_parts), encoding="utf-8")

    for g in ORDER:
        buckets[g].sort()
        parts = [HEADER.format(name=g)]
        for s, name in buckets[g]:
            e = spans[name][1]
            seg = "".join(lines[s - 1:e])
            seg = seg.replace("@app.", "@router.")
            # usar registry para que el mock se haga en un solo sitio
            seg = seg.replace("available_sources()",
                              "registry.available_sources()")
            seg = seg.replace("get_scraper(", "registry.get_scraper(")
            parts.append(seg)
            parts.append("\n\n")
        (ROUTERS / f"{g}.py").write_text(
            "".join(parts), encoding="utf-8")
        print(f"{g}: {len(buckets[g])} funciones")

    # nuevo main.py delgado
    new_main = '''"""App FastAPI (Fase 1: factory delgado; endpoints en app/routers/*).

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
from app.database.models import User  # noqa: F401
from app.database.models import UserProfile  # noqa: F401
from app.database.models import UserRichProfile  # noqa: F401
from app.routers import auth as auth_router
from app.routers import discovery as discovery_router
from app.routers import jobs as jobs_router
from app.routers import profiles as profiles_router
from app.routers import search_profiles as search_profiles_router
from app.routers import system as system_router
# Re-export para compatibilidad con tests que parchan app.main.get_scraper
from app.scraper.registry import available_sources  # noqa: F401
from app.scraper.registry import get_scraper  # noqa: F401
from app.services.job_service import backfill_fingerprints


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import DB_BACKEND

    if DB_BACKEND == "firestore":
        from app.database.firestore_client import FirestoreDatabase

        db = FirestoreDatabase()
        backfill_fingerprints(db)
    else:
        Base.metadata.create_all(bind=engine)
        ensure_columns()
        db = SessionLocal()
        try:
            backfill_fingerprints(db)
        finally:
            db.close()
    import os as _os
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
app.include_router(profiles_router.router)
app.include_router(search_profiles_router.router)
app.include_router(discovery_router.router)
app.include_router(jobs_router.router)
'''
    MAIN.write_text(new_main, encoding="utf-8")
    print("main.py reescrito como factory delgado")


if __name__ == "__main__":
    main()
