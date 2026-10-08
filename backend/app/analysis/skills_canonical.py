"""Canon de skills: texto extraido -> validada -> canonica -> almacenada.

Capa unica de normalizacion para ofertas, CV/perfil y matching.
No une por parecido: solo alias explicitos. `BI` solo NO es `Power BI`,
`Business Intelligence` NO es `Power BI` salvo alias declarado.
"""
from __future__ import annotations

import re
import unicodedata

# Palabras/frases estructurales que jamas son skills por si solas (ES+EN).
_GENERIC_STOP: set[str] = {
    "tool", "tools", "herramienta", "herramientas",
    "skill", "skills", "habilidad", "habilidades",
    "competencia", "competencias", "competency", "competencies",
    "requirement", "requirements", "requisito", "requisitos",
    "requerimiento", "requerimientos",
    "knowledge", "conocimiento", "conocimientos",
    "experience", "experiencia", "experiencias",
    "professional", "profesional", "profesionales",
    "responsibility", "responsibilities", "responsabilidad",
    "responsabilidades", "funcion", "funciones",
    "qualification", "qualifications", "calificacion",
    "ability", "abilities", "capacidad", "capacidades",
    "aptitud", "aptitudes", "actitud", "actitudes",
    "other", "otro", "otros", "general", "varios", "etc",
    "information", "informacion", "data", "datos",
    "management", "manejo", "gestion",
    "office", "ofimatica", "ofimatico", "computador", "computadora",
    "informatica", "sistemas", "tecnologia", "tecnologias",
    "technology", "technologies",
}

# Frases de prosa que indican sentencia, no skill (subcadena, ya normalizada).
_GENERIC_PHRASES = (
    "anos de experiencia", "ano de experiencia", "experiencia laboral",
    "se requiere", "se necesita", "se busca", "se ofrece", "se valorara",
    "capacidad para", "habilidad para", "conocimiento en", "conocimientos en",
    "manejo de informacion", "consolidar informacion",
)

# Alias explicito normalizado -> etiqueta canonica de exhibicion.
# Clave: _norm_key(alias). Solo equivalencias seguras.
_ALIASES: dict[str, str] = {}


def _norm_key(text: str) -> str:
    value = unicodedata.normalize("NFKD", (text or "").lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    # Conserva + # . para c#, .net, node.js ; el resto a espacio.
    value = re.sub(r"[^a-z0-9+#. ]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _add(canonical: str, *aliases: str) -> None:
    for alias in (canonical, *aliases):
        key = _norm_key(alias)
        if key and key not in _ALIASES:
            _ALIASES[key] = canonical


# --- BI / datos (variantes ortograficas, NUNCA hiperonimos genericos) ---
_add("Power BI", "powerbi", "power-bi", "power_bi", "pbi", "power bi desktop")
_add("Power Query", "powerquery", "power-query", "power query editor", "m language", "lenguaje m")
_add("DAX", "dax language")
_add("Power Pivot", "powerpivot", "power-pivot")
_add("Google Colab", "google colab", "colab", "google colaboratory")
_add("Power Automate", "powerautomate", "microsoft flow", "flujos power automate")
_add("Power Apps", "powerapps", "power-apps")
_add("Power Platform", "powerplatform")
_add("Tableau", "tableau desktop", "tableau prep")
_add("Qlik", "qlikview", "qliksense", "qlik sense")
_add("Looker", "looker studio", "google data studio", "data studio")
_add("Excel", "microsoft excel", "ms excel", "excel basico")
_add("Excel avanzado", "excel advanced", "tablas dinamicas", "tablas pivot",
      "power pivot excel", "buscav", "buscarv", "xlookup")
_add("Google Sheets", "google sheets", "hojas de calculo google", "gsheets")
_add("SQL", "structured query language", "lenguaje sql", "sql language")
_add("PostgreSQL", "postgres", "postgresql", "psql", "postgre sql")
_add("MySQL", "mysql", "my sql")
_add("SQL Server", "sqlserver", "sql-server", "microsoft sql server", "ms sql",
      "t-sql", "tsql", "ssms")
_add("SSIS", "ssis", "sql server integration services")
_add("SSRS", "ssrs", "sql server reporting services")
_add("SSAS", "ssas", "sql server analysis services")
_add("SQLite", "sqlite", "sqlite3")
_add("MariaDB", "mariadb")
_add("Oracle", "oracle db", "oracle database", "pl/sql", "plsql")
_add("MongoDB", "mongo db", "mongodb", "mongo")
_add("Snowflake", "snowflake")
_add("BigQuery", "big query", "google bigquery")
_add("Redshift", "amazon redshift")
_add("Databricks", "databricks")
_add("Redis", "redis")
_add("Elasticsearch", "elasticsearch", "elastic search")
_add("ETL", "elt", "etl/elt")
_add("Airflow", "apache airflow")
_add("Apache Spark", "spark", "pyspark", "apache spark")
_add("dbt", "data build tool")
_add("Kafka", "apache kafka")
_add("Hadoop", "apache hadoop")
_add("Talend", "talend")
_add("Alteryx", "alteryx")
_add("KNIME", "knime")

# --- Lenguajes / librerias ---
_add("Python", "python3", "python 3", "py")
_add("Pandas", "pandas python", "pd")
_add("NumPy", "numpy")
_add("Scikit-learn", "scikit learn", "sklearn", "scikit-learn")
_add("TensorFlow", "tensorflow")
_add("PyTorch", "pytorch", "torch")
_add("OpenCV", "opencv", "cv2")
_add("YOLO", "yolo")
_add("YOLOv8", "yolov8", "yolo v8", "yolo-v8", "yolo v8n")
_add("R", "r language", "r studio", "rstudio")
_add("Java", "java 8", "java 11", "java 17")
_add("JavaScript", "javascript", "js", "ecmascript")
_add("TypeScript", "typescript", "ts")
_add("C#", "c#", "c sharp", "csharp", ".net", "dotnet", "asp.net", "asp net")
_add("C++", "c++", "cpp")
_add("PHP", "php")
_add("Go", "golang")
_add("Rust", "rust")
_add("Kotlin", "kotlin")
_add("Swift", "swift")
_add("Scala", "scala")
_add("MATLAB", "matlab")
_add("HTML", "html5")
_add("CSS", "css3")
_add("Bash", "bash", "shell scripting", "shell")
_add("PowerShell", "powershell")

# --- Frameworks / web / APIs ---
_add("React", "reactjs", "react.js", "react js")
_add("Angular", "angular")
_add("Vue", "vuejs", "vue.js")
_add("Next.js", "nextjs", "next.js", "next js")
_add("Node.js", "nodejs", "node.js", "node js", "node")
_add("Express", "expressjs", "express.js")
_add("NestJS", "nestjs", "nest.js")
_add("Django", "django rest", "django-rest-framework", "django rest framework", "drf")
_add("Flask", "flask")
_add("FastAPI", "fastapi", "fast api")
_add("Spring", "spring boot", "springboot", "spring framework")
_add("Laravel", "laravel")
_add(".NET", ".net core", ".net")
_add("REST", "rest api", "rest apis", "api rest", "apis rest", "restful")
_add("GraphQL", "graphql")
_add("Microservicios", "microservicios", "microservices", "microservice")
_add("Selenium", "selenium")
_add("JUnit", "junit")

# --- Nube / DevOps ---
_add("AWS", "amazon web services", "amazon aws")
_add("Azure", "microsoft azure", "azure data factory", "azure synapse", "synapse")
_add("GCP", "google cloud", "google cloud platform", "gcp")
_add("Docker", "docker")
_add("Kubernetes", "kubernetes", "k8s")
_add("Terraform", "terraform")
_add("Ansible", "ansible")
_add("Jenkins", "jenkins")
_add("CI/CD", "ci/cd", "ci cd", "continuous integration", "integracion continua")
_add("Git", "git")
_add("GitHub", "github")
_add("GitLab", "gitlab")
_add("Linux", "linux", "gnu/linux")
_add("Jupyter", "jupyter notebook", "jupyterlab", "jupyter lab")
_add("Visual Studio Code", "visual studio code", "vs code", "vscode")
_add("Firebase", "firebase")
_add("Supabase", "supabase")

# --- Gestion / metodologias ---
_add("Scrum", "scrum")
_add("Kanban", "kanban")
_add("Metodologías ágiles", "metodologias agiles", "agile", "agil", "metodologia agil")
_add("Jira", "jira")
_add("Trello", "trello")
_add("Notion", "notion")
_add("MS Project", "ms project", "microsoft project")
_add("Gestión de proyectos", "gestion de proyectos", "project management")
_add("PMP", "pmp")
_add("Lean", "lean")
_add("Six Sigma", "six sigma")
_add("SAP", "sap", "sap mm", "sap fi", "sap business one")
_add("Salesforce", "salesforce")
_add("Prompt Engineering", "prompt engineering", "ingenieria de prompts")
_add("Machine Learning", "machine learning", "ml", "aprendizaje automatico")
_add("Deep Learning", "deep learning", "dl")
_add("Computer Vision", "computer vision", "vision por computador", "vision artificial")
_add("NLP", "nlp", "procesamiento de lenguaje natural", "natural language processing")
_add("IA generativa", "ia generativa", "generative ai", "genai", "chatgpt")
_add("MLOps", "mlops")
_add("Automatización", "automatizacion", "automatizar", "automatizar procesos",
      "automatizacion de procesos", "automatizar reportes")
_add("VBA", "vba", "macros", "macro excel", "visual basic for applications")
_add("APIs", "api", "apis", "integraciones")
_add("Dashboards", "dashboard", "dashboards", "tablero", "tableros",
      "tablero de control", "tableros de control")
_add("Indicadores", "indicadores", "indicador", "kpi", "kpis",
      "seguimiento de indicadores", "key performance indicators")
_add("Análisis de datos", "analisis de datos", "data analysis", "analisis de informacion",
      "analizar datos", "eda", "exploratory data analysis", "analisis exploratorio")
_add("Limpieza de datos", "limpieza de datos", "limpiar datos", "data cleansing",
      "data cleaning", "depuracion de datos", "calidad de datos")
_add("Transformación de datos", "transformacion de datos", "transformar datos",
      "procesamiento de datos", "procesar datos", "data processing")
_add("Modelado de datos", "modelado de datos", "modelo de datos", "data modeling",
      "modelo dimensional", "modelo estrella", "data modeling")
_add("Visualización de datos", "visualizacion de datos", "data visualization",
      "visualizacion de informacion")
_add("Análisis estadístico", "analisis estadistico", "estadistica",
      "estadistica descriptiva", "statistics")
_add("Minería de datos", "mineria de datos", "data mining")
_add("Reportes", "reporte", "reportes", "generar reportes", "informes de gestion",
      "generacion de reportes")
_add("Bases de datos", "base de datos", "bases de datos", "database", "databases",
      "administracion de bases de datos")

# --- Blandas canonicas ---
_add("Trabajo en equipo", "trabajo en equipo", "teamwork", "equipo")
_add("Comunicación", "comunicacion", "communication", "comunicacion efectiva")
_add("Liderazgo", "liderazgo", "leadership", "lider")
_add("Orientación a resultados", "orientacion a resultados", "orientado a resultados")
_add("Atención al detalle", "atencion al detalle", "attention to detail")
_add("Pensamiento analítico", "pensamiento analitico", "analytical thinking",
      "pensamiento critico", "pensamiento crítico")
_add("Resolución de problemas", "resolucion de problemas", "problem solving")
_add("Adaptabilidad", "adaptabilidad", "adaptability")
_add("Gestión del tiempo", "gestion del tiempo", "time management")

# Jerarquia para matching: dialecto/herramienta implica base (no a la inversa).
_IMPLIES: dict[str, set[str]] = {
    "PostgreSQL": {"SQL", "Bases de datos"},
    "MySQL": {"SQL", "Bases de datos"},
    "SQL Server": {"SQL", "Bases de datos"},
    "SQLite": {"SQL", "Bases de datos"},
    "MariaDB": {"SQL", "Bases de datos"},
    "Oracle": {"SQL", "Bases de datos"},
    "MongoDB": {"Bases de datos"},
    "Snowflake": {"SQL", "Bases de datos"},
    "BigQuery": {"SQL", "Bases de datos"},
    "Power Query": {"ETL"},
    "DAX": {"Power BI"},
    "Power Pivot": {"Excel avanzado"},
    "Pandas": {"Python"},
    "NumPy": {"Python"},
    "Scikit-learn": {"Python", "Machine Learning"},
    "FastAPI": {"Python", "REST"},
    "Flask": {"Python", "REST"},
    "Django": {"Python", "REST"},
    "React": {"JavaScript"},
    "Next.js": {"React", "JavaScript"},
    "Node.js": {"JavaScript"},
}


def canonical_key(text: str) -> str:
    """Clave de comparacion (minusculas, sin tildes, espacios colapsados)."""
    return _norm_key(text)


def is_generic(raw: str) -> bool:
    """True si el texto es estructural/generico y no puede ser skill."""
    text = (raw or "").strip()
    if not text:
        return True
    key = _norm_key(text)
    if not key or len(key) < 2:
        return True
    if key in _GENERIC_STOP:
        return True
    tokens = key.split()
    if tokens and all(t in _GENERIC_STOP for t in tokens):
        return True
    for phrase in _GENERIC_PHRASES:
        if phrase in key:
            return True
    # Prosa: 5+ palabras casi nunca es una skill etiquetable.
    if len(tokens) > 4:
        return True
    if len(text) > 60:
        return True
    return False


def canonicalize_one(raw: str) -> str | None:
    """Texto extraido -> etiqueta canonica, o None si no es skill valida.

    - `PowerBi` -> `Power BI` (alias).
    - `BI` solo -> None (ambiguo, no asumir Power BI).
    - `Business Intelligence` -> None salvo contexto (no alias a Power BI).
    - Desconocido plausible (ej. `Supabase`) se preserva limpio, no se inventa.
    """
    text = (raw or "").strip()
    text = re.sub(r"\s+", " ", text).strip(" .;,")
    if not text:
        return None
    key = _norm_key(text)
    if not key:
        return None
    # Tokens de una letra que SI son skills (lenguajes). Excepcion
    # controlada antes del filtro generico.
    if key in {"r", "c"}:
        return {"r": "R", "c": "C"}[key]
    if is_generic(text):
        return None
    # Anti-falsos-positivos explicitos: nunca inferir producto desde hiperonimo.
    if key in {"bi", "b i"}:
        return None
    if key in {"business intelligence", "inteligencia de negocios",
               "inteligencia de negocio"}:
        # Concepto valido pero distinto producto; se conserva como tal.
        return "Business Intelligence"
    hit = _ALIASES.get(key)
    if hit:
        return hit
    # Sin alias: conservar solo si parece etiqueta (1-3 palabras, tecnico).
    tokens = key.split()
    if len(tokens) > 3 or len(text) > 40:
        return None
    if re.fullmatch(r"\d+", key):
        return None
    return text.strip()


def _split_compound(raw: str) -> list[str] | None:
    """`Comunicación y trabajo en equipo` -> [Comunicación, Trabajo...].

    Solo si TODAS las partes resuelven a canonicas conocidas; si no,
    None (no partir `Seguridad y salud en el trabajo` u otros conceptos
    unitarios). Controlado: nunca por parecido, solo alias exactos.
    """
    text = (raw or "").strip()
    if " y " not in text.lower() and "/" not in text:
        return None
    parts = [p.strip(" .;") for p in re.split(r"\s+y\s+|/", text) if p.strip(" .;")]
    if len(parts) < 2:
        return None
    resolved = [canonicalize_one(p) for p in parts]
    if all(resolved):
        return list(resolved)
    return None


def normalize_skill_list(items: list | None, limit: int = 100) -> list[str]:
    """Lista bruta -> canonicas unicas en orden, sin genericos ni duplicados."""
    out: list[str] = []
    seen: set[str] = set()

    def push(canon: str | None) -> None:
        if not canon:
            return
        key = canonical_key(canon)
        if key and key not in seen:
            seen.add(key)
            out.append(canon)

    for raw in (items or [])[:limit]:
        text = re.sub(r"\s+", " ", str(raw or "")).strip(" .;,")
        if not text:
            continue
        canon = canonicalize_one(text)
        if canon:
            push(canon)
            continue
        # Compuesto tipo `A y B`: solo si ambas partes son skills conocidas.
        parts = _split_compound(text)
        if parts:
            for part in parts:
                push(part)
            continue
        # Etiqueta corta no reconocida (ej. `Seguridad y salud en el
        # trabajo`): se preserva como vino (nada se destruye) salvo prosa
        # evidente (>6 palabras, frases genericas o solo-stopwords).
        key = canonical_key(text)
        tokens = key.split()
        if 1 <= len(tokens) <= 6 and len(text) <= 60:
            if key in _GENERIC_STOP or all(
                t in _GENERIC_STOP for t in tokens
            ):
                continue
            if any(p in key for p in _GENERIC_PHRASES):
                continue
            if re.fullmatch(r"\d+", key):
                continue
            push(text)
    return out


def known_variants(canonical: str) -> list[str]:
    """Canonicas + todos sus alias declarados (para evidencia literal).

    `Limpieza de datos` -> [Limpieza de datos, data cleaning, ...]:
    basta que UNA variante exista en el texto para descartar invento.
    """
    key = canonical_key(canonical or "")
    if not key:
        return []
    out = [canonical]
    for alias_key, canon in _ALIASES.items():
        if canon == canonical and alias_key != key:
            out.append(alias_key)
    seen: set[str] = set()
    unique = []
    for item in out:
        k = canonical_key(item)
        if k not in seen:
            seen.add(k)
            unique.append(item)
    return unique


def expand_implied(skills: list[str]) -> set[str]:
    """Canonicas + sus bases implicadas (PostgreSQL => SQL). Para matching."""
    out = {canonical_key(s) for s in (skills or []) if s}
    out.discard("")
    for skill in list(skills or []):
        canon = canonicalize_one(str(skill)) or str(skill).strip()
        for implied in _IMPLIES.get(canon, ()):
            out.add(canonical_key(implied))
    return out
