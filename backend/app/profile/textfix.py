"""Reparacion mecanica de palabras pegadas ('utilizandoExcel').

Origen tipico: copiar texto desde un PDF (la extraccion pierde espacios
alrededor de negritas) y pegarlo en el perfil. El pipeline reproduce el
texto tal cual, asi que el pegado llega hasta el PDF generado.

Estrategia conservadora (nunca inventa, todo cambio se reporta):
- Solo separa alrededor de TERMINOS TECNICOS conocidos (vocabulario de
  signals + extras del matcher) o en el caso mecanico `palabra-comun +
  numero` ('de10.000'). El resto del texto no se toca.
- 'JavaScript', 'GitHub', 'YOLOv8', 'utf8', 'PowerBI' se conservan
  porque el vocabulario (o la keep-list) los reconoce.
"""
from __future__ import annotations

import re
import unicodedata

# Palabras funcionales que SI pueden ir pegadas a un numero por error
# de extraccion ('de10.000' -> 'de 10.000'). 'base'/'log'/'utf' NO estan:
# 'base64', 'log4j', 'utf8' se conservan.
_COMMON_WORDS = frozenset(
    "de la el en y a con para por los las un una del al se que como "
    "mas su sus este esta estos estas entre sobre hacia desde hasta "
    "sin tras ante bajo durante mediante segun cada todo todos todas "
    "muy tambien ademas donde cuando porque pero aunque es son fue "
    "tiene tienen usa uso hace hacen".split()
)

# Terminos que siempre se conservan pegados aunque tengan mayusculas
# internas o numeros.
_KEEP_GLUED = frozenset(
    "javascript typescript powershell powerpoint github gitlab gitflow "
    "linkedin youtube macos ios iphone ipad devops powerbi utf8 base64 "
    "log4j i18n yolov8 h264 mp3 nodejs".split()
)

_vocab: list[str] | None = None
_vocab_set: set[str] | None = None


def _tech_vocab() -> tuple[list[str], set[str]]:
    """Tokens tecnicos (lista larga-primero + conjunto normalizado)."""
    global _vocab, _vocab_set
    if _vocab is not None:
        return _vocab, _vocab_set or set()
    from app.analysis import signals as _signals

    terms: set[str] = set()
    for label, variants, _tier in _signals.SKILLS:
        for variant in [label, *variants]:
            for token in _signals.norm(variant).split(" "):
                if len(token) >= 3:
                    terms.add(token)
    for tool in _signals.TOOLS:
        for token in _signals.norm(tool).split(" "):
            if len(token) >= 3:
                terms.add(token)
    try:
        from app.adapt.matcher import EXTRA_SKILLS as _extras

        for extra in _extras:
            key = _signals.norm(extra)
            if len(key) >= 3:
                terms.add(key)
    except Exception:  # noqa: BLE001
        pass
    for extra in ("yolov8", "opencv", "roboflow", "scikit-learn",
                  "fastapi", "pandas", "numpy", "github", "linkedin"):
        terms.add(extra)
    _vocab = sorted(terms, key=len, reverse=True)
    _vocab_set = set(terms)
    return _vocab, _vocab_set


def _norm_token(token: str) -> str:
    text = unicodedata.normalize("NFKD", token.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


_LETTERS = r"[A-Za-záéíóúñÁÉÍÓÚÑ]+"


def _split_token(token: str) -> str:
    """Separa UN token pegado o lo devuelve intacto."""
    vocab, vocab_set = _tech_vocab()
    # Puntuacion final aparte ('enSQL.' -> nucleo 'enSQL' + '.').
    core, tail = token, ""
    while core and core[-1] in ".,;:!?":
        tail = core[-1] + tail
        core = core[:-1]
    if not core:
        return token
    if _norm_token(core) in _KEEP_GLUED or _norm_token(core) in vocab_set:
        return token
    for term in vocab:
        if len(term) >= len(core):
            continue
        # Pegado ANTES del termino: 'utilizandoExcel', 'enSQL'.
        before = re.match(r"^(.+)" + re.escape(term) + r"$", core,
                          re.IGNORECASE)
        if before and re.fullmatch(_LETTERS, before.group(1)):
            cut = len(before.group(1))
            return core[:cut] + " " + core[cut:] + tail
        # Pegado DESPUES del termino: 'Pythonpara'.
        after = re.match(re.escape(term) + r"(.+)$", core, re.IGNORECASE)
        if after and re.fullmatch(_LETTERS, after.group(1)):
            cut = len(core) - len(after.group(1))
            return core[:cut] + " " + core[cut:] + tail
    # Caso mecanico: palabra comun + numero ('de10.000').
    match = re.match(r"^([A-Za-záéíóúñ]+)(\d[\d.,]*)$", core)
    if match and _norm_token(match.group(1)) in _COMMON_WORDS:
        return f"{match.group(1)} {match.group(2)}{tail}"
    return token


def fix_spacing(text: str | None) -> tuple[str, list[str]]:
    """Devuelve (texto, cambios['a' -> 'b']). Solo toca lo anclado."""
    if not text or not isinstance(text, str):
        return text or "", []
    changes: list[str] = []
    out: list[str] = []
    for token in re.split(r"(\s+)", text):
        if not token or token.isspace():
            out.append(token)
            continue
        fixed = _split_token(token)
        if fixed != token:
            changes.append(f"{token} -> {fixed}")
        out.append(fixed)
    return "".join(out), changes
