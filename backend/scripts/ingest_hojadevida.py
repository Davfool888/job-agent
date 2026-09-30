"""Ingesta real: HOJADEVIDA/Hoja_de_vida{1,2} -> base_cv.json.

- Parsea ambos .tex (fuente de verdad, nada inventado).
- Fusiona por union con dedup (personal de CV2, secciones unidas).
- Siembra perspectivas iniciales SOLO con bullets copiados del .tex:
  data vs comercial, clasificadas por palabras clave deterministicas.
- Guarda via save_rich_profile (valida) y reporta advertencias.
Uso: .venv/Scripts/python.exe backend/scripts/ingest_hojadevida.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.cv.latex_import import parse_latex_profile  # noqa: E402
from app.services.job_service import save_rich_profile  # noqa: E402

HOJA = ROOT / "HOJADEVIDA"

DATA_KEYWORDS = (
    "power bi", "dax", "power query", "excel", "python", "sql", "pandas",
    "numpy", "datos", "data", "analis", "indicador", "kpi", "dashboard",
    "reporte", "etl", "automatiz", "limpieza", "transform", "segment",
    "cruce", "duplicado", "informe", "tablero", "query", "bi ",
    "estadistic",
)
COMMERCIAL_KEYWORDS = (
    "comercial", "cliente", "empresa", "venta", "fideliz", "seguimiento",
    "producto financiero", "credito", "cdt", "tarjeta", "deposito",
    "nomina", "cooperativa", "atencion", "gestion",
)


def _classify(bullet: str) -> str:
    low = bullet.lower()
    data_hit = any(k in low for k in DATA_KEYWORDS)
    com_hit = any(k in low for k in COMMERCIAL_KEYWORDS)
    if data_hit and not com_hit:
        return "data"
    if com_hit and not data_hit:
        return "commercial"
    return "both"


def _dedup(items: list) -> list:
    seen, out = set(), []
    for item in items:
        key = item if isinstance(item, str) else str(sorted(
            item.items()) if isinstance(item, dict) else item)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _merge_profiles(base: dict, extra: dict) -> dict:
    from app.analysis.signals import norm

    merged = dict(base)
    for key in ("education", "projects", "languages", "certifications"):
        merged[key] = _dedup(list(merged.get(key) or [])
                             + list(extra.get(key) or []))
    # Experiencia: mismo cargo+empresa = mismo empleo (los dos CV lo
    # describen distinto) -> fusiona bullets por union, sin inventar.
    seen: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for exp in list(merged.get("experience") or []) + list(extra.get("experience") or []):
        key = (norm(exp.get("title")), norm(exp.get("company")))
        if key not in seen:
            seen[key] = dict(exp)
            order.append(key)
        else:
            current = seen[key]
            current["bullets"] = _dedup(
                list(current.get("bullets") or []) + list(exp.get("bullets") or []))
            for field in ("period", "description"):
                if not (current.get(field) or "").strip() and exp.get(field):
                    current[field] = exp[field]
    merged["experience"] = [seen[k] for k in order]
    # Proyectos: mismo nombre = mismo proyecto -> fusiona descripcion.
    # Incluye abreviaturas ("IA" vs "Inteligencia Artificial"): si los
    # nombres normalizados comparten un prefijo largo, es el mismo.
    def _same_project(a: str, b: str) -> bool:
        na, nb = norm(a), norm(b)
        if not na or not nb:
            return False
        if na == nb:
            return True
        common = 0
        for ca, cb in zip(na, nb):
            if ca != cb:
                break
            common += 1
        return common >= 30

    seen_p: list[dict] = []
    for proj in list(merged.get("projects") or []):
        target = None
        for existing in seen_p:
            if _same_project(existing.get("name", ""), proj.get("name", "")):
                target = existing
                break
        if target is None:
            seen_p.append(dict(proj))
            continue
        for field in ("description",):
            if len(str(proj.get(field) or "")) > len(str(target.get(field) or "")):
                target[field] = proj[field]
        target["technologies"] = _dedup(
            list(target.get("technologies") or [])
            + list(proj.get("technologies") or []))
        if len(str(proj.get("name") or "")) > len(str(target.get("name") or "")):
            target["name"] = proj["name"]
    merged["projects"] = seen_p
    for group, items in (extra.get("skills") or {}).items():
        merged.setdefault("skills", {}).setdefault(group, [])
        merged["skills"][group] = _dedup(
            list(merged["skills"].get(group) or []) + list(items or []))
    if not (merged.get("professional_summary") or "").strip():
        merged["professional_summary"] = extra.get("professional_summary", "")
    for key in ("personal",):
        for field, value in (extra.get(key) or {}).items():
            if value and not (merged.get(key) or {}).get(field):
                merged.setdefault(key, {})[field] = value
    return merged


def _seed_perspectives(profile: dict) -> dict:
    """Crea perspectivas data/comercial desde bullets reales."""
    for exp in profile.get("experience", []):
        if exp.get("perspectives"):
            continue
        bullets = [b for b in (exp.get("bullets") or []) if str(b).strip()]
        data_b = [b for b in bullets if _classify(b) in ("data", "both")]
        com_b = [b for b in bullets if _classify(b) in ("commercial", "both")]
        perspectives = []
        if data_b:
            perspectives.append({
                "id": "data-analytics",
                "label": "Data Analytics",
                "description": " ".join(data_b),
                "skills": [],
                "tools": [],
                "domains": [],
                "roles": ["DATA_ANALYST", "BI_ANALYST"],
            })
        if com_b and com_b != data_b:
            perspectives.append({
                "id": "comercial",
                "label": "Comercial",
                "description": " ".join(com_b),
                "skills": [],
                "tools": [],
                "domains": [],
                "roles": ["BUSINESS_ANALYST"],
            })
        exp["perspectives"] = perspectives
    return profile


def main() -> None:
    tex1 = (HOJA / "Hoja_de_vida1").read_text(encoding="utf-8")
    tex2 = (HOJA / "Hoja_de_vida2").read_text(encoding="utf-8")
    r1 = parse_latex_profile(tex1)
    r2 = parse_latex_profile(tex2)
    print("CV1 warnings:", r1["warnings"])
    print("CV2 warnings:", r2["warnings"])
    merged = _merge_profiles(r2["profile"], r1["profile"])
    merged = _seed_perspectives(merged)
    # Skills base unificadas para validacion de perspectivas.
    saved = save_rich_profile(merged)
    print("guardado. advertencias:", saved.get("warnings"))
    prof = saved["profile"]
    print("experiencia:", len(prof.get("experience", [])),
          "| proyectos:", len(prof.get("projects", [])),
          "| educacion:", len(prof.get("education", [])))
    for exp in prof.get("experience", []):
        print(" -", exp.get("title"), "| perspectivas:",
              [p["label"] for p in exp.get("perspectives", [])])


if __name__ == "__main__":
    main()
