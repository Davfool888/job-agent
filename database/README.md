# database/ — Firebase Firestore para job-agent

> **Estado: CONECTADO.** Proyecto `job-agent-davfo`, región
> `southamerica-east1`. El backend escribe en Firestore con
> `DB_BACKEND=firestore` (ver `backend/.env`). SQLite queda como respaldo.

Capa independiente de datos. Arquitectura real:

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

## 5. Migración SQLite → Firestore (ejecutada 2026-09-30)

Script: `database/scripts/migrate_sqlite_to_firestore.py` (idempotente:
omite documentos existentes).

| SQLite (`backend/data/job_agent.db`) | Firestore |
|---|---|
| `jobs` (1 tabla) | `jobs/` (doc id = id SQLite en zero-padding) + `applications/` para `applied` |
| `status`: `new/kept/discarded/opened/applied` | `NEW/SAVED/DISCARDED/VIEWED/APPLIED` (mapeo en `firestore_repo.py`) |
| `discard_reason` (texto ES) | código (`LOW_MATCH`…) + `discard_reason_raw` con el texto original |
| `modality` (texto libre) | enum (`REMOTE/HYBRID/ONSITE`) + `modality_raw` |
| `salary` (texto) | objeto `{raw, min, max, currency}` (parseo COP conservador) |
| `matched/missing_skills`, `evidence`, `discovered_by`, `times_seen`, `fingerprint` | mismos campos (arrays nativos en Firestore) |
| `profile` (singleton JSON) | `profiles/base` (estructura `schema/profiles.json` + `legacy_skills_flat`) |
| `data/cvs/job_<ID>/cv.{tex,pdf}` | siguen en disco; metadatos en `cvs/` al generar |
| Sin eventos de postulación | `applications/{id}/events/` con `APPLICATION_CREATED` |

Orden dedup (igual que hoy): `source+external_id` → `url` → `content_hash` → `title+company+location`.

## 6. Conexión backend (implementada)

- `backend/app/database/firestore_client.py`: Admin SDK (solo servidor),
  soporta ruta al JSON, JSON inline (`FIREBASE_SERVICE_ACCOUNT_JSON`,
  pensado para Render) y emulador.
- `backend/app/database/firestore_repo.py`: repositorio completo con la
  misma firma que `job_service` (crear/actualizar/vista/descarte/evento/
  CV/interacciones). `job_service` despacha según `DB_BACKEND`.
- IDs: secuenciales zero-padded (`counters/jobs`), siempre `str` en la API
  (ambos motores) para no romper el frontend.
- Endpoints nuevos: `GET /applications`, `GET /applications/{id}`.
- Variables: `DB_BACKEND`, `FIREBASE_PROJECT_ID`, `FIRESTORE_DATABASE`,
  `GOOGLE_APPLICATION_CREDENTIALS` (ver `backend/.env.example`).
- En Render: define `DB_BACKEND=firestore`,
  `FIREBASE_SERVICE_ACCOUNT_JSON=<contenido del JSON>` y redespliega.
  Los PDF siguen generándose en disco local (Storage queda preparado
  en el esquema `cvs`).
