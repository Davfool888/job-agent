"""Lexico de dominios/industrias para relevancia de perspectivas.

Palabras clave normalizadas (minusculas, sin tildes) por dominio.
Se usa para industry_match y domain_match sin llamadas IA.
"""
from __future__ import annotations

from app.analysis.signals import norm
from app.analysis.signals import phrases_found

DOMAINS: dict[str, list[str]] = {
    "banking": [
        "banco", "bancario", "bancaria", "nomina", "cuenta de nomina",
        "credito", "creditos", "cartera", "cdt", "tarjeta de credito",
        "deposito", "depositos", "sucursal", "oficina bancaria",
        "producto bancario", "productos bancarios", "fidelizacion",
        "cliente empresarial", "empresas cooperativas",
    ],
    "finance": [
        "finanzas", "financiero", "financiera", "presupuesto",
        "contabilidad", "tesoreria", "auditoria", "riesgo crediticio",
        "indicadores financieros", "estados financieros", "facturacion",
        "cobranza", "pagos", "inversion",
    ],
    "retail": [
        "retail", "tienda", "ventas", "vendedor", "punto de venta",
        "inventario", "cliente final", "comercial", "vitrina",
    ],
    "health": [
        "salud", "hospital", "clinica", "paciente", "eps", "ips",
        "historia clinica", "farmacia",
    ],
    "education": ["educacion", "universidad", "colegio", "estudiante", "academico"],
    "government": ["gobierno", "publico", "alcaldia", "ministerio", "estado"],
    "telecom": ["telecomunicaciones", "internet", "telefonia", "redes"],
    "logistics": ["logistica", "bodega", "transporte", "inventarios", "distribucion"],
    "tech": [
        "software", "tecnologia", "startup", "desarrollo de software",
        "aplicacion", "plataforma", "sistema de informacion",
    ],
}

# Sectores del perfil (texto libre del usuario) -> dominio canonico.
SECTOR_ALIASES: dict[str, str] = {
    "bancario": "banking",
    "banca": "banking",
    "financiero": "finance",
    "finanzas": "finance",
    "salud": "health",
    "educativo": "education",
    "retail": "retail",
    "ventas": "retail",
    "tecnologia": "tech",
    "software": "tech",
    "logistica": "logistics",
    "gobierno": "government",
    "telecomunicaciones": "telecom",
}


def detect_domains(text: str | None) -> list[str]:
    """Dominios presentes en un texto (oferta o perfil)."""
    normalized = norm(text)
    return [
        domain
        for domain, keywords in DOMAINS.items()
        if phrases_found(normalized, keywords)
    ]


def canonical_domain(raw: str | None) -> str | None:
    """Normaliza un dominio/sector libre del perfil a canonico."""
    normalized = norm(raw)
    if not normalized:
        return None
    if normalized in DOMAINS:
        return normalized
    for alias, domain in SECTOR_ALIASES.items():
        if alias in normalized or normalized in alias:
            return domain
    return None
