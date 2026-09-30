# database/ — Firebase Firestore para job-agent

Capa independiente de datos. **No toca `backend/` ni `frontend/`** (siguen
con SQLite hasta la migración). Arquitectura objetivo:

```text
React/Vercel → FastAPI/Render → Firebase Admin SDK → Firestore + Storage
```

## 1. Crear el proyecto Firebase

1. https://console.firebase.google.com → Add project (`job-agent-xxxx`).
2. **Firestore Database** → Create database → modo **producción** (las
   reglas de este repo niegan todo por defecto) → región `us-central1`
   (o la más cercana).
3. **Storage** → Get started → bucket `job-agent-xxxx.appspot.com`
   (solo metadatos en Firestore; los PDF viven aquí: `cvs/job_<id>/`).
4. **Service account**: Project settings → Service accounts →
   Generate new private key → guarda el JSON **fuera del repo**
   (ej. `C:/secrets/job-agent-key.json`). Nunca a GitHub.

## 2. Variables de entorno

```powershell
Copy-Item database\.env.example database\.env
# editar: FIREBASE_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS=...
```

| Variable | Uso |
|---|---|
| `FIREBASE_PROJECT_ID` | Proyecto (emulador y despliegue) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta al JSON de la cuenta de servicio (solo backend/scripts, jamás frontend) |
| `FIRESTORE_EMULATOR_HOST` | `localhost:8080` para desarrollo sin gastar cuota |
| `FIREBASE_STORAGE_BUCKET` | Bucket de PDFs |

## 3. Colecciones y relaciones

```text
profiles/base ─referencia──► jobs/{id} ──analysis──► (campos del doc)
   (skills, exp.)      │        ├─► cvs/{id} (job_id, version; application_id al enviar)
                       │        ├─► interactions (job_id, JOB_VIEWED, ...)
                       │        └─► applications/{id} (job_id, cv_id exacto)
                       │                 └─► events/{id} (línea de tiempo)
                       └─► analytics/daily_YYYY-MM-DD (rollups opcionales)
```

Esquemas: `schema/*.json`. Reglas: `firestore.rules` (denegar todo;
el backend usa Admin SDK que las omite). Índices: `firestore.indexes.json`
(`firebase deploy --only firestore:indexes,firestore:rules` con Firebase CLI).

## 4. Scripts

```powershell
cd database
pip install -r requirements.txt   # entorno aparte, no el del backend

python scripts/validate_schema.py  # offline, sin Firebase: esquemas + seed + rules + indexes
python scripts/create_collections.py
python scripts/seed_database.py
```

Con emulador: `firebase emulators:start --only firestore` y
`FIRESTORE_EMULATOR_HOST=localhost:8080`.

## 5. Migración SQLite → Firestore (conceptual, pendiente)

| SQLite (`backend/data/job_agent.db`) | Firestore |
|---|---|
| `jobs` (1 tabla) | `jobs/` + `applications/` (separar: `status`→ job status; `applied_at`/`application_status` → `applications/`) |
| `status`: `new/kept/discarded/opened/applied` | `NEW/VIEWED/SAVED/DISCARDED/APPLIED/...` (+ `interactions` para vistas: `viewed`, `view_count`) |
| `discard_reason` (texto ES) | `discard_reason` (código `LOW_MATCH`… + `discard_note`); mapa ES→código en `schema/jobs.json` vía seed |
| `matched/missing_skills`, `evidence`, `discovered_by`, `times_seen`, `fingerprint` | mismos campos en `jobs/` |
| `profile` (singleton JSON) | `profiles/base` (estructura `schema/profiles.json`) |
| `data/cvs/job_<ID>/cv.{tex,pdf}` | subir a Storage `cvs/job_<id>/cv_v1.*` + doc en `cvs/` |
| Sin eventos de postulación | `applications/{id}/events/` (nuevo; reconstruir parcial desde `applied_at`) |

Orden dedup (igual que hoy): `source+external_id` → `url` → `content_hash` → `title+company+location`.

## 6. Conexión backend (cuando se migre)

Nuevo módulo `backend/app/db/firestore_client.py` con Admin SDK
(credenciales solo en servidor), repositorio por colección con la misma
firma que `job_service` (crear/actualizar/vista/descarte/evento/CV),
y endpoints sin cambios de contrato para el frontend. Los agentes ya
están separados por responsabilidad (`agents/`), solo cambian de
`Session` a repositorio.
