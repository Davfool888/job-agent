import os
from pathlib import Path

from dotenv import load_dotenv

# backend/.env siempre, sin importar desde donde se ejecuta uvicorn/pytest.
# __file__ = backend/app/config.py -> parent.parent = backend/
BASE_DIR = Path(__file__).resolve().parent.parent
# Raiz del proyecto (para .env compartido y data/cvs).
ROOT_DIR = BASE_DIR.parent
# La raiz aporta defaults; backend/.env tiene prioridad (no rompe lo actual).
load_dotenv(ROOT_DIR / ".env")
load_dotenv(BASE_DIR / ".env")

APP_NAME = os.getenv("APP_NAME", "job-agent")

# Cuenta administradora: la unica que ve y edita el perfil base global
# (singleton Profile + base_cv.json). Cualquier otro usuario con sesion
# usa su propio perfil, que empieza en blanco.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "davfool888@gmail.com").strip().lower()


def is_admin_email(email: str | None) -> bool:
    return bool(email) and email.strip().lower() == ADMIN_EMAIL

_DEFAULT_DB = f"sqlite:///{(BASE_DIR / 'data' / 'job_agent.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DB)

# --- Motor de persistencia: sqlite (local, defecto) o firestore (nube).
# Cambiar a firestore requiere FIREBASE_PROJECT_ID + credenciales Admin SDK.
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").strip().lower()
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "(default)")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

COMPUTRABAJO_BASE_URL = os.getenv(
    "COMPUTRABAJO_BASE_URL",
    "https://co.computrabajo.com",
).rstrip("/")

MAGNETO_BASE_URL = os.getenv(
    "MAGNETO_BASE_URL",
    "https://www.magneto365.com",
).rstrip("/")

ELEMPLEO_BASE_URL = os.getenv(
    "ELEMPLEO_BASE_URL",
    "https://www.elempleo.com",
).rstrip("/")

INDEED_BASE_URL = os.getenv(
    "INDEED_BASE_URL",
    "https://co.indeed.com",
).rstrip("/")

LINKEDIN_BASE_URL = os.getenv(
    "LINKEDIN_BASE_URL",
    "https://www.linkedin.com",
).rstrip("/")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
)

# Origenes permitidos por CORS (coma-separados). Incluye el frontend
# de Vercel en produccion + localhost para desarrollo. Sin "*" permanente:
# allow_credentials=True es incompatible con "*" y expondria la API.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://job-agent-puce-eight.vercel.app",
    ).split(",")
    if origin.strip()
]

# --- Fuentes habilitadas (fase inicial: computrabajo + linkedin) ---
COMPUTRABAJO_ENABLED = os.getenv("COMPUTRABAJO_ENABLED", "true").lower() == "true"
LINKEDIN_ENABLED = os.getenv("LINKEDIN_ENABLED", "true").lower() == "true"

# --- Pesos del matching (services/matching_service). Suman 100. ---
MATCH_WEIGHTS = {
    "title": int(os.getenv("MATCH_W_TITLE", "20")),
    "skills": int(os.getenv("MATCH_W_SKILLS", "30")),
    "responsibilities": int(os.getenv("MATCH_W_RESPONSIBILITIES", "30")),
    "tools": int(os.getenv("MATCH_W_TOOLS", "20")),
}

# --- Umbrales de generacion de CV (§13) ---
# match >= AUTO -> generar automaticamente.
# REVIEW <= match < AUTO -> dejar para revision (solo con force=true).
# match < REVIEW -> no generar.
CV_AUTO_THRESHOLD = float(os.getenv("CV_GENERATION_THRESHOLD", "75"))
CV_REVIEW_THRESHOLD = float(os.getenv("CV_REVIEW_THRESHOLD", "50"))

# --- AI Router (§8) ---
AI_PROVIDER_ORDER = [
    p.strip()
    for p in os.getenv("AI_PROVIDER_ORDER", "gemini,openai_compat,rule_based").split(",")
    if p.strip()
]
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_COMPAT_BASE_URL = os.getenv(
    "OPENAI_COMPAT_BASE_URL", "https://api.openai.com/v1"
)
OPENAI_COMPAT_API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "")
OPENAI_COMPAT_MODEL = os.getenv("OPENAI_COMPAT_MODEL", "gpt-4o-mini")

# --- Scheduler de busqueda automatica ---
# En Render (gratuito) la instancia duerme: ademas del scheduler interno,
# un cron externo puede llamar POST /scheduler/tick (ver SCHEDULER_CRON_SECRET).
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60"))
SCHEDULER_CRON_SECRET = os.getenv("SCHEDULER_CRON_SECRET", "")

CVS_DIR = BASE_DIR / "data" / "cvs"
PROFILES_DIR = BASE_DIR / "data" / "profiles"
BASE_CV_PATH = PROFILES_DIR / "base_cv.json"

# --- CVs de referencia por perfil de busqueda (PDFs subidos en /search).
# Un PDF por perfil: sirve de ejemplo de estilo para generar CVs
# personalizados de las ofertas que ese perfil encuentre.
PROFILE_CVS_DIR = BASE_DIR / "data" / "profile_cvs"
MAX_CV_BYTES = int(os.getenv("MAX_CV_BYTES", str(10 * 1024 * 1024)))
# Cuantos CVs de referencia entran al prompt y con cuantos caracteres c/u.
REFERENCE_CV_MAX_PROFILES = 2
REFERENCE_CV_MAX_CHARS = 3000

# --- Adaptar-perfil: CV personalizado HTML -> PDF (Chromium) ---
ADAPT_CVS_DIR = BASE_DIR / "data" / "adapt_cvs"
ADAPT_PDF_TIMEOUT_MS = int(os.getenv("ADAPT_PDF_TIMEOUT_MS", "60000"))
# Pulido opcional del resumen con LLM (apagado = 100% local).
ADAPT_LLM_ENABLED = os.getenv("ADAPT_LLM_ENABLED", "false").lower() == "true"
