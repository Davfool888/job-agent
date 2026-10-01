"""CVs de referencia por perfil de busqueda (PDFs subidos en /search).

Un PDF por perfil (`data/profile_cvs/profile_<id>/cv.pdf` + `cv.txt`
con el texto extraido). Aqui solo metadatos: SQLite (tabla profile_cvs)
o Firestore (coleccion profile_cvs). Esos textos alimentan como ejemplos
la generacion de CVs personalizados (ver `reference_texts_for_job`).
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.database.firestore_client import is_firestore
from app.database.models import ProfileCV


def _parse_ids(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return [str(v) for v in (parsed or []) if str(v).strip()]
        except ValueError:
            return []
    return []


def cv_dir(profile_id) -> Path:
    from app.config import PROFILE_CVS_DIR

    directory = PROFILE_CVS_DIR / f"profile_{profile_id}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def pdf_path(profile_id) -> Path:
    return cv_dir(profile_id) / "cv.pdf"


def txt_path(profile_id) -> Path:
    return cv_dir(profile_id) / "cv.txt"


def extract_text(content: bytes) -> tuple[str, int]:
    """Texto plano + N.o de paginas. Lanza ValueError si es ilegible."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = len(reader.pages)
        parts = [(page.extract_text() or "") for page in reader.pages]
    except Exception as error:
        raise ValueError(f"No se pudo leer el PDF: {error}")
    text = "\n".join(p.strip() for p in parts if p and p.strip()).strip()
    return text, pages


def _to_dict(profile_id, data: dict, download: bool = True) -> dict:
    out = {
        "profile_id": str(profile_id),
        "filename": data.get("filename") or "cv.pdf",
        "size_bytes": int(data.get("size_bytes") or 0),
        "pages": int(data.get("pages") or 0),
        "chars": int(data.get("chars") or 0),
    }
    uploaded = data.get("uploaded_at")
    out["uploaded_at"] = (
        uploaded.isoformat() if hasattr(uploaded, "isoformat")
        else uploaded
    )
    out["has_text"] = out["chars"] > 0
    if download:
        out["download_url"] = (
            f"/search-profiles/{profile_id}/cv/download")
    return out


def save_profile_cv(
    db: Session, profile_id, filename: str, content: bytes
) -> dict:
    """Valida, guarda archivos en disco y metadatos. Reemplaza el previo."""
    from app.config import MAX_CV_BYTES

    if not content.startswith(b"%PDF-"):
        raise ValueError("El archivo no es un PDF valido.")
    if len(content) > MAX_CV_BYTES:
        raise ValueError(
            f"El PDF supera el maximo de {MAX_CV_BYTES // 1024 // 1024} MB."
        )
    text, pages = extract_text(content)
    pdf_path(profile_id).write_bytes(content)
    txt_path(profile_id).write_text(text, encoding="utf-8")
    now = datetime.utcnow()
    meta = {
        "filename": (filename or "cv.pdf")[:300],
        "size_bytes": len(content),
        "pages": pages,
        "chars": len(text),
        "uploaded_at": now,
    }
    if is_firestore(db):
        from app.database import firestore_repo as fs

        fs.save_profile_cv(db, profile_id, meta)
    else:
        row = db.query(ProfileCV).filter(
            ProfileCV.profile_id == str(profile_id)).first()
        if not row:
            row = ProfileCV(profile_id=str(profile_id))
            db.add(row)
        row.filename = meta["filename"]
        row.size_bytes = meta["size_bytes"]
        row.pages = meta["pages"]
        row.chars = meta["chars"]
        row.uploaded_at = now
        db.add(row)
        db.commit()
    return _to_dict(profile_id, meta)


def get_profile_cv(db: Session, profile_id) -> dict | None:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        data = fs.get_profile_cv(db, profile_id)
        return _to_dict(profile_id, data) if data else None
    row = db.query(ProfileCV).filter(
        ProfileCV.profile_id == str(profile_id)).first()
    if not row:
        return None
    # Sin fila no hay nada; si falta el archivo, se reporta igual.
    return _to_dict(profile_id, {
        "filename": row.filename,
        "size_bytes": row.size_bytes,
        "pages": row.pages,
        "chars": row.chars,
        "uploaded_at": row.uploaded_at,
    })


def delete_profile_cv(db: Session, profile_id) -> bool:
    existed = get_profile_cv(db, profile_id) is not None
    for path in (pdf_path(profile_id), txt_path(profile_id)):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    if is_firestore(db):
        from app.database import firestore_repo as fs

        fs.delete_profile_cv(db, profile_id)
    else:
        db.query(ProfileCV).filter(
            ProfileCV.profile_id == str(profile_id)).delete(
                synchronize_session=False)
        db.commit()
    return existed


def reference_texts_for_job(db: Session, job) -> list[dict]:
    """Textos de CVs de referencia de los perfiles que encontraron la
    oferta. [{profile_id, label, text}]. Vacio si no hay."""
    from app.config import REFERENCE_CV_MAX_CHARS
    from app.config import REFERENCE_CV_MAX_PROFILES

    ids = _parse_ids(getattr(job, "search_profile_ids", None))
    references: list[dict] = []
    for pid in ids[:REFERENCE_CV_MAX_PROFILES]:
        meta = get_profile_cv(db, pid)
        if not meta or not meta["has_text"]:
            continue
        try:
            text = txt_path(pid).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue
        label = f"perfil {pid}"
        try:
            from app.services import search_profiles as profiles

            found = profiles.get_profile(db, pid)
            if found and found.get("name"):
                label = found["name"]
        except Exception:  # noqa: BLE001
            pass
        references.append({
            "profile_id": str(pid),
            "label": label,
            "text": text[:REFERENCE_CV_MAX_CHARS],
        })
    return references
