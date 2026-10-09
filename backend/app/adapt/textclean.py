"""Limpieza mecanica de espaciado para el CV adaptado (pre-render).

Origen tipico: texto importado del PDF (la extraccion pierde espacios
alrededor de negritas/cambios de linea) que el pipeline reproduce tal
cual, mas la reescritura LLM que lo conserva. Esto NO adivina palabras:
solo aplica reglas con frontera detectable y conserva intacto todo lo
demas:

- colapsa espacios multiples / saltos de linea,
- quita espacios antes de `, ; : . ! ?`,
- agrega espacio tras `, ; :` + letra, tras `.` + mayuscula (fin de
  oracion, sin tocar decimales como 10.000), tras `)` + letra y antes
  de `(` (Demanda(en desarrollo)),
- separa camelCase con frontera minuscula->MAYUSCULA
  (informacionEmpresarial; McDonald/eBay intactos: 1 minuscula antes),
  acronimo + minusculas (BIpara -> BI para)
  y minusculas + acronimo (productosCDT -> productos CDT),
- separa digito + minusculas (10.000registros), sin tocar niveles (b2),
  versiones (v2), 3D, Python3, EC2 ni YOLOv8/utf8,
- espacia guiones largos (Cooperativas– Analisis),
- re-pega vocales sueltas partidas (Gestion e -> Gestione nunca;
  Gestion é -> Gestioné),
- nunca toca terminos de la keep-list tecnica ni nombres propios con
  mayuscula intermedia (McDonald).

Idempotente: clean(clean(x)) == clean(x). Solo se aplica a prosa
libre (resumen, descripciones, bullets, titulos de item); jamas a
identidad (nombres, email, telefono) ni empresas/instituciones.
"""
from __future__ import annotations

import re
import unicodedata


def _norm_token(token: str) -> str:
    text = unicodedata.normalize("NFKD", token.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


_KEEP: frozenset[str] | None = None


def _keep() -> frozenset[str]:
    """Terminos que jamas se parten (vocabulario + keep-list)."""
    global _KEEP
    if _KEEP is not None:
        return _KEEP
    keep: set[str] = set()
    try:
        from app.profile import textfix as _tf

        vocab, _vocab_set = _tf._tech_vocab()
        keep.update(vocab)
        keep.update(_tf._KEEP_GLUED)
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.analysis import skills_canonical as _sc

        keep.update(_sc._ALIASES)
        for canon in set(_sc._ALIASES.values()):
            keep.add(_sc.canonical_key(canon))
    except Exception:  # noqa: BLE001
        pass
    for extra in ("yolov8", "opencv", "roboflow", "scikit-learn",
                  "fastapi", "pandas", "numpy", "github", "linkedin",
                  "javascript", "typescript", "powerbi", "utf8", "base64",
                  "log4j", "i18n", "nodejs"):
        keep.add(extra)
    _KEEP = frozenset(keep)
    return _KEEP


_LOWER = "a-záéíóúñ"
_UPPER = "A-ZÁÉÍÓÚÑ"


def _guarded(token: str, build) -> str:
    """Aplica build(token) salvo termino protegido."""
    if _norm_token(token) in _keep():
        return token
    return build(token)


def _split_token_cases(token: str) -> str:
    """Separa UN token por fronteras mecanicas seguras."""
    core, tail = token, ""
    while core and core[-1] in ".,;:!?":
        tail = core[-1] + tail
        core = core[:-1]
    if not core:
        return token

    def build(core: str) -> str:
        out = core
        # camelCase: minuscula->MAYUSCULA con 2+ minusculas antes
        # (informacionEmpresarial sí; McDonald/eBay no: 1 sola minuscula).
        out = re.sub(f"([{_LOWER}]{{2,}})([{_UPPER}])", r"\1 \2", out)
        # ACRONIMO + minusculas (BIpara -> BI para; RESTAPIs -> REST APIs).
        out = re.sub(f"([{_UPPER}]{{2,}})([{_LOWER}]{{2,}})", r"\1 \2", out)
        # minusculas + ACRONIMO (productosCDT -> productos CDT).
        out = re.sub(f"([{_LOWER}]{{2,}})([{_UPPER}]{{2,}})", r"\1 \2", out)
        # digito + minusculas (10.000registros -> 10.000 registros).
        # Se exigen 2+ digitos: niveles como b2 o versiones (v2) intactos.
        # Letra + digito NO se toca (Python3, EC2, Davfool888 intactos).
        out = re.sub(f"(\\d{{2,}})([{_LOWER}])", r"\1 \2", out)
        return out

    return _guarded(core, build) + tail


def clean_text(text: str | None) -> str:
    """Normaliza espaciado. Entrada no-str -> ""."""
    if not text or not isinstance(text, str):
        return ""
    # NFC: la extraccion de PDFs suele emitir tildes descompuestas
    # (e + ´) y las clases [áéíóú] no las ven sin normalizar.
    out = unicodedata.normalize("NFC", str(text))
    out = re.sub(r"\s+", " ", out).strip()
    if not out:
        return ""
    # Espacio antes de puntuacion (sin tocar '...').
    out = re.sub(r"\s+([,;:!?])(?!\.)", r"\1", out)
    out = re.sub(r"\s+\.(?!\.)", ".", out)
    # Falta espacio despues de puntuacion. URLs/emails/horas a salvo:
    # ':' no seguido de '/' ni parte de '10:30' (digito:digito).
    out = re.sub(f"([,;])([{_LOWER}{_UPPER}0-9(])", r"\1 \2", out)
    out = re.sub(f"(:)(?!/)([{_LOWER}{_UPPER}(])", r"\1 \2", out)
    # Fin de oracion pegado (decisiones.Analicé). Decimales (10.000) y
    # abreviaturas con mayuscula previa (EE.UU.) no se tocan: antes de
    # '.' se exige minuscula.
    out = re.sub(f"([{_LOWER}])\\.([{_UPPER}])", r"\1. \2", out)
    # Parentesis pegados: ')X' y 'X('.
    out = re.sub(f"(\\))([{_LOWER}{_UPPER}])", r"\1 \2", out)
    out = re.sub(f"([{_LOWER}{_UPPER}])(\\()", r"\1 \2", out)
    # Guion largo sin espacios (Cooperativas– Analisis).
    out = re.sub(r"(\S)\s*[–—]\s*(\S)", r"\1 – \2", out)
    # Corte de palabra por salto de linea ('procesa- miento' ->
    # 'procesamiento'). Solo guion pegado a letra + continuacion en
    # minusculas: rangos ('30 - 40'), 'pre- y post-' y fechas intactos.
    out = re.sub(f"([{_LOWER}{_UPPER}])-\\s+([{_LOWER}]{{2,}})", r"\1\2",
                 out)
    # Partes por token (camel, acronimos, digitos) con keep-list.
    out = "".join(
        _split_token_cases(tok) if not tok.isspace() else tok
        for tok in re.split(r"(\s+)", out)
    )
    # Segunda pasada tecnica: lo que quedo separado (ej. 'Pythonpara'
    # tras partir camel) se ancla a vocabulario conocido. Solo añade
    # espacios alrededor de terminos tecnicos; resto intacto.
    try:
        from app.profile.textfix import fix_spacing as _tech_fix

        out, _ = _tech_fix(out)
    except Exception:  # noqa: BLE001
        pass
    # Vocal suelta por extraccion ('Gestion é' -> 'Gestioné'). En
    # español ninguna palabra es una vocal acentuada sola.
    out = re.sub(f"([{_LOWER}{_UPPER}]{{3,}}) ([áéíóúÁÉÍÓÚ])\\b", r"\1\2",
                 out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


_PROSE_KEYS = ("summary", "description", "title", "name", "degree")


def clean_content(content: dict) -> dict:
    """Limpia la prosa del content in-place (devuelve el mismo dict).

    Campos: summary, titulos/nombres de item y descripciones/bullets de
    experiences, projects, education, other_studies y certifications.
    Identidad, empresas, instituciones, fechas, skills e idiomas intactos.
    """
    if not isinstance(content, dict):
        return content
    if isinstance(content.get("summary"), str):
        content["summary"] = clean_text(content["summary"])
    for section in ("experiences", "projects", "education",
                    "other_studies", "certifications"):
        items = content.get(section)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in _PROSE_KEYS:
                if isinstance(item.get(key), str):
                    item[key] = clean_text(item[key])
            bullets = item.get("bullets")
            if isinstance(bullets, list):
                item["bullets"] = [
                    clean_text(b) for b in bullets if str(b or "").strip()
                ]
    return content
