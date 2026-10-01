# Job Agent

Sistema de automatización de búsqueda y análisis de ofertas laborales.

- **backend/** — FastAPI + scrapers + agentes + IA + CV/LaTeX.
- **frontend/** — React + TypeScript + Vite (consume la API por HTTP).

## Arranque local

```powershell
# Terminal 1 — backend (desde job-agent/backend)
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (desde job-agent/frontend)
npm run dev
```

Frontend: http://localhost:5173 · API: http://localhost:8000/docs

## Variables de entorno

Copia `.env.example` (raíz) a `.env` y/o `backend/.env` (`backend/.env`
tiene prioridad). Nunca subas secretos. Sin API keys el sistema funciona
con análisis determinístico + fallback local.

## Pipeline

```text
Scrapers → Normalización → Deduplicación (external_id > URL > hash > huella)
  → Prefilter determinístico → Job Analysis Agent → [AI Router: solo ambiguos]
  → Role Classification → Matching (pesos .env) → BD → Frontend
Ofertas relevantes → CV Agent → contenido JSON → plantilla LaTeX fija
  → PDF (si hay pdflatex) → data/cvs/job_<ID>/ → Frontend
```

- Nada se auto-descarta: lo poco relevante se guarda con score bajo.
- El CV **solo** usa `backend/data/profiles/base_cv.json` (complétalo con
  tus datos; el sistema nunca inventa experiencia).
- Umbrales CV: `CV_GENERATION_THRESHOLD` (auto) y `CV_REVIEW_THRESHOLD`
  (revisión); bajo el mínimo solo con `{"force": true}`.
- Estados en BD en minúsculas (`new/kept/discarded/opened/applied`)
  ≡ NEW/KEPT/DISCARDED/APPLIED del diseño. `found_at` ≡ `created_at`.
- Abrir la URL original marca `opened`; nunca afirma postulación completada.

## Endpoints principales

Ofertas: `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/analysis`,
`PATCH /jobs/{id}/status`, `GET /jobs/{id}/detail`.
Búsqueda: `GET /jobs/search`, `POST /jobs/discover`, `GET /sources`,
`GET /discovery/packs`. Análisis: `POST /jobs/{id}/analyze`,
`POST /jobs/analyze-pending`. CV: `POST /jobs/{id}/cv`,
`GET /jobs/{id}/cv`, `GET /jobs/{id}/cv/download?format=pdf|tex`.
Búsqueda automática: `GET/POST /search-profiles`,
`GET/PUT/DELETE /search-profiles/{id}`,
`POST /search-profiles/{id}/run`, `GET /scheduler/status`,
`POST /scheduler/tick`.
Stats: `GET /stats`, `GET /analytics`, `GET /ai/status`, `GET /health`.

## Tests

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\frontend; npm run lint  # tsc + eslint; build con npm run build
```

## Ejecución automática / cloud (FASE 15)

El backend es stateless salvo SQLite: para servidor, usa Postgres
(`DATABASE_URL`) y un cron que llame `POST /jobs/discover` +
`POST /jobs/analyze-pending`. PDFs requieren `pdflatex` (TeX Live)
en el servidor; sin él se entrega el `.tex`.

## Despliegue en Render con Docker (RECOMENDADO para PDFs)

El proyecto incluye un `Dockerfile` en `backend/` que instala:
- **TeX Live** (pdflatex) → para CVs LaTeX (`/jobs/{id}/cv`)
- **Playwright + Chromium** → para "Adaptar perfil" (`/jobs/{id}/adapt-cv`)

### Pasos en Render Dashboard:

1. **New → Web Service** → Connect tu repo
2. **Runtime**: `Docker`
3. **Dockerfile Path**: `backend/Dockerfile`
4. **Docker Context**: `backend`
5. **Plan**: Free (o Starter para más RAM)
6. **Environment Variables** (Settings → Environment):
   ```
   DB_BACKEND=firestore
   FIREBASE_PROJECT_ID=tu-proyecto
   GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/firebase-key.json  # Archivo secreto
   GEMINI_API_KEY=...
   OPENAI_COMPAT_API_KEY=...
   ADMIN_EMAIL=tu@email.com
   FRONTEND_ORIGINS=https://tu-frontend.vercel.app,http://localhost:5173
   SCHEDULER_ENABLED=true
   SCHEDULER_CRON_SECRET=  # Se auto-genera si dejas vacío
   CV_GENERATION_THRESHOLD=75
   CV_REVIEW_THRESHOLD=50
   ```
7. **Secret Files**: Sube tu `firebase-service-account.json` como `firebase-key.json`
8. **Deploy**

> **RAM en plan gratuito (512MB)**: Chromium + pdflatex pueden ser justos.
> Si falla, usa plan **Starter (1GB)** o desactiva `ADAPT_LLM_ENABLED=false`.

### Variables clave para PDFs:
- `ADAPT_LLM_ENABLED=false` (ahorra RAM, usa resumen determinista)
- `SCHEDULER_CRON_SECRET` = auto-generado (para cron externo)

## Búsqueda automática cada ~10 min

Perfiles en la sección **Búsqueda** del frontend (`/search`) o vía API.
El backend ejecuta los activos según su frecuencia (APScheduler en
proceso, `SCHEDULER_ENABLED=true`, tick cada `SCHEDULER_INTERVAL_SECONDS`).

**Importante en Render (plan gratuito):** la instancia duerme sin tráfico
y con el PC apagado el scheduler interno se detiene. Para búsqueda real
24/7 configura un cron externo gratuito (cron-job.org) cada 10 min hacia:

```text
POST https://tu-backend.onrender.com/scheduler/tick
```

con header `X-Cron-Secret: <SCHEDULER_CRON_SECRET>` (define el secreto en
Render; sin secreto configurado el endpoint es público). Cada tick ejecuta
solo los perfiles vencidos, con lock anti-solapamiento, y guarda en
Firestore. Al reabrir la plataforma, las nuevas aparecen en
**Ofertas → Recientes** (badge "N nuevas" + orden "Recién encontradas").
