"""Taxonomia de señales para descubrimiento y scoring de ofertas.

Todo el matching es deterministico sobre texto normalizado
(minusculas, sin tildes). Niveles de evidencia (requisito §12):

- STRONG: por si solas casi definen trabajo de datos/BI/python.
- MEDIUM: relevantes pero insuficientes aisladas.
- WEAK: correlacionadas; UNA sola evidencia debil NUNCA clasifica.
"""
from __future__ import annotations

import re
import unicodedata


def norm(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", (text or "").lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-z0-9 ]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def phrases_found(text_norm: str, phrases: list[str]) -> list[str]:
    """Devuelve las frases presentes con limites de palabra."""
    found = []
    for phrase in phrases:
        pattern = r"(?<!\w)" + re.escape(norm(phrase)) + r"(?!\w)"
        if re.search(pattern, text_norm):
            found.append(phrase)
    return found


# (etiqueta canonica, [alias], tier)
# tier: "strong" | "medium" | "weak"
SKILLS: list[tuple[str, list[str], str]] = [
    ("Power BI", ["power bi", "powerbi"], "strong"),
    ("SQL", ["sql", "postgresql", "mysql", "sql server", "oracle db"], "strong"),
    ("ETL", ["etl", "elt", "airflow", "pipelines de datos", "data pipelines"], "strong"),
    ("DAX", ["dax"], "strong"),
    ("Limpieza de datos", ["limpieza de datos", "limpiar datos", "depurar bases de datos", "depuracion de datos", "calidad de datos", "data cleansing"], "strong"),
    ("Modelado de datos", ["modelado de datos", "modelo de datos", "data modeling", "modelo dimensional", "estrella"], "strong"),
    ("Transformación de datos", ["transformacion de datos", "transformar datos", "procesamiento de datos", "procesar datos"], "strong"),
    ("Análisis de datos", ["analisis de datos", "analisis de informacion", "analisis de bases de datos", "analizar datos", "analizar informacion", "data analysis"], "strong"),
    ("Python", ["python"], "medium"),
    ("Pandas", ["pandas"], "medium"),
    ("NumPy", ["numpy"], "medium"),
    ("Power Query", ["power query", "powerquery", "m language"], "medium"),
    ("Visualización de datos", ["visualizacion de datos", "visualizacion de informacion", "data visualization"], "medium"),
    ("Análisis estadístico", ["analisis estadistico", "estadistica descriptiva", "estadistica"], "medium"),
    ("Automatización", ["automatizacion", "automatizar", "automatizar reportes", "automatizar procesos", "macros", "vba", "scripts"], "medium"),
    ("Excel avanzado", ["excel avanzado", "tablas dinamicas", "tablas dinámicas", "power pivot", "buscav", "buscarv", "xlookup"], "medium"),
    ("Indicadores", ["indicadores", "kpi", "kpis", "seguimiento de indicadores"], "medium"),
    ("Reportes", ["reportes", "generar reportes", "construir reportes", "informes de gestion", "informes gerenciales"], "medium"),
    ("Dashboards", ["dashboard", "dashboards", "tableros", "tablero de control"], "strong"),
    ("Bases de datos", ["bases de datos", "base de datos", "database"], "medium"),
    ("APIs", ["api", "apis", "rest", "integraciones"], "medium"),
    ("Django", ["django"], "medium"),
    ("Flask", ["flask"], "medium"),
    ("FastAPI", ["fastapi"], "medium"),
    ("Azure", ["azure", "synapse", "data factory"], "medium"),
    ("AWS", ["aws", "redshift", "athena", "glue"], "medium"),
    ("Excel", ["excel"], "weak"),
    ("Informes", ["informes", "elaborar informes", "generar informes"], "weak"),
    ("Manejo de información", ["manejo de informacion", "consolidar informacion", "consolidacion de informacion", "digitar", "digitacion"], "weak"),
    ("Computador", ["computador", "office", "word", "herramientas ofimaticas"], "weak"),
]

# Patrones de responsabilidad: (etiqueta, [variantes], tier)
RESPONSIBILITIES: list[tuple[str, list[str], str]] = [
    ("Analizar datos", ["analizar datos", "analisis de datos", "interpretar datos"], "strong"),
    ("Analizar bases de datos", ["analizar bases de datos", "analisis de bases de datos"], "strong"),
    ("Limpiar datos", ["limpiar datos", "limpieza de datos", "depurar datos"], "strong"),
    ("Construir dashboards", ["construir dashboards", "crear dashboards", "elaborar dashboards", "crear tableros"], "strong"),
    ("Generar KPIs", ["generar kpis", "generar indicadores", "elaborar indicadores", "definir kpis", "elaboracion de indicadores", "elaboracion de kpis"], "strong"),
    ("Automatizar reportes", ["automatizar reportes", "automatizacion de reportes"], "strong"),
    ("Generar reportes", ["generar reportes", "construir reportes", "elaborar reportes", "presentar reportes", "generacion de reportes", "elaboracion de reportes"], "medium"),
    ("Generar informes", ["generar informes", "elaborar informes", "preparar informes", "generacion de informes", "elaboracion de informes"], "medium"),
    ("Consolidar información", ["consolidar informacion", "consolidacion de informacion", "integrar bases de datos", "integrar informacion"], "medium"),
    ("Extraer información", ["extraer informacion", "extraccion de informacion", "mineria de datos"], "medium"),
    ("Seguimiento de indicadores", ["seguimiento de indicadores", "seguimiento a indicadores", "monitoreo de indicadores"], "medium"),
    ("Visualizar información", ["visualizacion de informacion", "visualizar datos", "presentar datos"], "medium"),
    ("Analizar información", ["analizar informacion", "analisis de informacion"], "medium"),
    ("Procesar datos", ["procesar datos", "procesamiento de datos"], "medium"),
    ("Transformar datos", ["transformar datos", "transformacion de datos"], "medium"),
]

# Herramientas (para el componente tools del score).
TOOLS: list[str] = [
    "power bi", "excel", "sql", "python", "pandas", "numpy", "tableau",
    "looker", "qlik", "dax", "power query", "airflow", "spark", "azure",
    "aws", "postgresql", "mysql", "sql server", "oracle", "sap",
    "salesforce", "r ", "jupyter", "git", "docker", "kubernetes",
    "django", "flask", "fastapi", "javascript", "react", "etl",
]

# Roles: title_keys (ganan el rol por titulo), content keys por tier.
ROLES: dict[str, dict[str, list[str]]] = {
    "DATA_ANALYST": {
        "titles": ["analista de datos", "analista datos", "data analyst",
                   "data analytics", "analista de informacion",
                   "auxiliar de datos", "tecnico de datos", "técnico de datos",
                   "profesional de datos", "especialista de datos",
                   "analista bi", "bi analyst"],
        "strong": ["analisis de datos", "analisis de bases de datos",
                   "limpieza de datos", "power bi", "dashboards",
                   "analista de datos", "data analyst"],
        "medium": ["excel avanzado", "indicadores", "kpis", "reportes",
                   "sql", "pandas", "visualizacion de datos",
                   "automatizacion", "bases de datos"],
    },
    "DATA_ENGINEER": {
        "titles": ["ingeniero de datos", "data engineer", "ingeniero datos"],
        "strong": ["etl", "airflow", "spark", "pipelines de datos",
                   "modelado de datos", "data engineer"],
        "medium": ["python", "sql", "azure", "aws", "bases de datos",
                   "transformacion de datos"],
    },
    "BI_ANALYST": {
        "titles": ["bi analyst", "analista bi", "business intelligence",
                   "inteligencia de negocios", "analista de inteligencia"],
        "strong": ["power bi", "dax", "power query", "dashboards",
                   "business intelligence"],
        "medium": ["kpis", "indicadores", "sql", "reportes", "etl"],
    },
    "BI_DEVELOPER": {
        "titles": ["desarrollador bi", "bi developer", "desarrollador power bi"],
        "strong": ["dax", "power query", "modelado de datos", "power bi"],
        "medium": ["sql", "etl", "dashboards"],
    },
    "DATA_SCIENTIST": {
        "titles": ["cientifico de datos", "científico de datos",
                   "data scientist", "cientifico datos"],
        "strong": ["machine learning", "modelos predictivos",
                   "data scientist", "deep learning"],
        "medium": ["python", "pandas", "numpy", "estadistica",
                   "analisis estadistico"],
    },
    "PYTHON_DEVELOPER": {
        "titles": ["python developer", "desarrollador python",
                   "programador python", "backend python",
                   "software developer python"],
        "strong": ["python", "django", "flask", "fastapi"],
        "medium": ["apis", "pandas", "sql", "git"],
    },
    "SOFTWARE_DEVELOPER": {
        "titles": ["software developer", "desarrollador de software",
                   "desarrollador full stack", "desarrollador fullstack",
                   "desarrollador web", "programador"],
        "strong": ["apis", "microservicios"],
        "medium": ["javascript", "react", "git", "python", "sql", "docker"],
    },
    "DATABASE_ANALYST": {
        "titles": ["analista sql", "sql analyst", "database analyst",
                   "analista de bases de datos", "analista de informacion"],
        "strong": ["sql", "modelado de datos",
                   "administracion de bases de datos", "database analyst"],
        "medium": ["postgresql", "mysql", "sql server", "etl",
                   "bases de datos"],
    },
    "REPORTING_ANALYST": {
        "titles": ["analista de reportes", "reporting analyst",
                   "analista de informes"],
        "strong": ["generar reportes", "reporting analyst"],
        "medium": ["excel avanzado", "macros", "power bi", "informes",
                   "indicadores"],
    },
    "OPERATIONS_ANALYST": {
        "titles": ["analista de operaciones", "operations analyst",
                   "analista de procesos", "analista operativo"],
        "strong": ["seguimiento de indicadores"],
        "medium": ["indicadores", "kpis", "mejora de procesos",
                   "automatizacion", "reportes"],
    },
    "BUSINESS_ANALYST": {
        "titles": ["analista de negocio", "business analyst",
                   "analista funcional", "analista de requerimientos"],
        "strong": ["business analyst"],
        "medium": ["requerimientos", "procesos de negocio", "documentacion",
                   "stakeholders", "historias de usuario"],
    },
    "FINANCIAL_ANALYST": {
        "titles": ["analista financiero", "financial analyst",
                   "analista de finanzas"],
        "strong": ["financial analyst"],
        "medium": ["finanzas", "presupuestos", "contabilidad", "sap",
                   "excel avanzado"],
    },
}

WEAK_ONLY_MAX_ROLE = "OTHER"

TIER_POINTS = {"strong": 3, "medium": 1, "weak": 0}
# Clasificar rol exige: (a) >=1 strong, o (b) titulo del rol + >=1 medium,
# y en todo caso >= ROLE_MIN_POINTS puntos de evidencia del rol.
ROLE_MIN_POINTS = 4
