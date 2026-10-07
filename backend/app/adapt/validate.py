"""Validacion pre-render del contenido del CV.

Se ejecuta DESPUES de cualquier transformacion IA y ANTES de
renderizar: comprueba que skills/tecnologias existan en el perfil,
que no haya hechos/cifras/empresas/fechas nuevas y que se respeten
los limites de pdf_config. Si algo falla, el llamador conserva el
contenido original (snapshot previo a IA) en vez de generar contenido
no verificado. Pura: no muta nada, solo reporta.
"""
from __future__ import annotations


def _numbers(text: str) -> set[str]:
    import re as _re

    return set(_re.findall(r"\d[\d.,]*%?", str(text or "")))


def _profile_numbers(profile: dict) -> set[str]:
    """Todos los numeros presentes en el perfil display (texto)."""
    found: set[str] = set()

    def walk(value) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, (str, int, float)):
            found.update(_numbers(value))

    walk(profile or {})
    return found


def _profile_companies(profile: dict) -> set[str]:
    """Empresas/instituciones reales del perfil (normalizadas)."""
    from app.analysis.signals import norm

    companies: set[str] = set()
    for section in ("experiences", "experience", "education", "projects",
                    "certifications"):
        for item in (profile or {}).get(section) or []:
            if not isinstance(item, dict):
                continue
            for key in ("company", "institution"):
                name = str(item.get(key) or "").strip()
                if name:
                    companies.add(norm(name))
    return companies


def validate_pre_render(content: dict, profile: dict,
                        pdf_config: dict | None = None) -> tuple[bool, list[str]]:
    """Devuelve (ok, issues). ok=False exige conservar el original."""
    from app.adapt.audit import _content_terms, _profile_terms
    from app.adapt.html_renderer import _parse_ymd
    from app.analysis.signals import norm

    issues: list[str] = []
    content = content or {}
    profile = profile or {}
    real = _profile_terms(profile)
    declared = _content_terms(content)

    # 1. Skills/tecnologias/idiomas existen en el perfil.
    for bucket in ("skills", "technologies", "languages"):
        for term in declared[bucket]:
            if norm(term) not in real:
                issues.append(
                    f"termino sin respaldo en el perfil: '{term}'")

    # 2. Sin cifras nuevas: todo numero del contenido esta en el perfil.
    allowed_numbers = _profile_numbers(profile)
    for section in ("experiences", "education", "projects",
                    "certifications"):
        for item in content.get(section) or []:
            if not isinstance(item, dict):
                continue
            blob = " ".join(str(item.get(k) or "") for k in
                            ("title", "name", "degree", "company",
                             "institution", "description"))
            for number in _numbers(blob):
                if number not in allowed_numbers:
                    issues.append(
                        f"cifra nueva '{number}' en "
                        f"'{str(item.get('title') or item.get('name') or '')[:40]}'")
                    break

    # 3. Empresas/instituciones reales.
    real_companies = _profile_companies(profile)
    for section in ("experiences", "education", "projects",
                    "certifications"):
        for item in content.get(section) or []:
            if not isinstance(item, dict):
                continue
            for key in ("company", "institution"):
                name = str(item.get(key) or "").strip()
                if name and norm(name) not in real_companies:
                    issues.append(
                        f"organizacion nueva: '{name[:60]}'")
                    break

    # 4. Fechas validas (parseables o vacias/Actualidad).
    for section in ("experiences", "education", "projects"):
        for item in content.get(section) or []:
            if not isinstance(item, dict):
                continue
            for key in ("start", "end", "start_date", "end_date"):
                value = item.get(key)
                if value and not _parse_ymd(str(value)):
                    issues.append(
                        f"fecha invalida '{value}' en "
                        f"'{str(item.get('title') or item.get('name') or '')[:40]}'")
                    break

    # 5. Limites de pdf_config.
    config = pdf_config or {}
    for key, label in (("experiences", "max_experiences"),
                       ("projects", "max_projects")):
        try:
            limit = int(config.get(label, 0) or 0)
        except (TypeError, ValueError):
            limit = 0
        count = len([i for i in (content.get(key) or [])
                     if isinstance(i, dict)])
        if limit > 0 and count > limit:
            issues.append(
                f"{key}: {count} > maximo configurado ({limit})")

    return (len(issues) == 0), issues
