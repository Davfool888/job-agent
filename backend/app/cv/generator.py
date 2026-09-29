"""Generador LaTeX/PDF (§11-§12): plantilla fija + contenido validado.

Estructura por oferta: data/cvs/job_<ID>/{analysis.json, cv_content.json,
cv.tex, cv.pdf?}. El PDF se compila solo si hay compilador (pdflatex);
si no, se entrega el .tex + aviso honesto (sin PDF falso).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from app.ai.schemas.cv_content import CVContent
from app.config import CVS_DIR

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "base_cv.tex"

_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(text: str | None) -> str:
    out = []
    for char in str(text or ""):
        out.append(_LATEX_ESCAPES.get(char, char))
    return "".join(out)


def _bullets(items: list[str]) -> str:
    items = [escape_latex(i) for i in items if str(i).strip()]
    if not items:
        return ""
    return "\\begin{itemize}\n" + "\n".join(
        f"\\item {item}" for item in items
    ) + "\n\\end{itemize}\n"


def _section(title: str, body: str) -> str:
    if not body.strip():
        return ""
    return f"\\section*{{{escape_latex(title)}}}\n{body}\n"


def render_tex(content: CVContent, personal: dict) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    contact = " | ".join(
        part for part in [
            personal.get("email", ""),
            personal.get("phone", ""),
            personal.get("location", ""),
            personal.get("linkedin", ""),
            personal.get("github", ""),
            personal.get("portfolio", ""),
        ] if str(part).strip()
    )

    exp_blocks = []
    for exp in content.selected_experience:
        header = " — ".join(
            str(exp.get(k, "")) for k in ("title", "company", "period")
            if str(exp.get(k, "")).strip()
        )
        bullets = exp.get("bullets") or exp.get("achievements") or []
        exp_blocks.append(
            f"\\subsection*{{{escape_latex(header)}}}\n"
            + _bullets([str(b) for b in bullets])
        )

    proj_blocks = []
    for proj in content.selected_projects:
        name = escape_latex(proj.get("name", "Proyecto"))
        techs = proj.get("technologies") or []
        tech_line = (
            f"\\textit{{{escape_latex(', '.join(str(t) for t in techs))}}}\n"
            if techs else ""
        )
        proj_blocks.append(
            f"\\subsection*{{{name}}}\n{tech_line}"
            f"{escape_latex(proj.get('description', ''))}\n"
        )

    edu_blocks = []
    for edu in content.education:
        line = " — ".join(
            str(edu.get(k, "")) for k in ("degree", "institution", "year")
            if str(edu.get(k, "")).strip()
        )
        if line:
            edu_blocks.append(f"{escape_latex(line)}\\\\\n")

    mapping = {
        "FULL_NAME": escape_latex(personal.get("full_name", "CV")),
        "TITLE_LINE": escape_latex(personal.get("title", "")) + "\n"
        if personal.get("title") else "",
        "CONTACT_LINE": escape_latex(contact) + "\n" if contact else "",
        "SUMMARY_SECTION": _section(
            "Resumen profesional", escape_latex(
                content.professional_summary) + "\n"
        ) if content.professional_summary.strip() else "",
        "EXPERIENCE_SECTION": _section(
            "Experiencia", "\n".join(exp_blocks)) if exp_blocks else "",
        "PROJECTS_SECTION": _section(
            "Proyectos", "\n".join(proj_blocks)) if proj_blocks else "",
        "SKILLS_SECTION": _section(
            "Habilidades",
            escape_latex(", ".join(content.skills)) + "\n",
        ) if content.skills else "",
        "EDUCATION_SECTION": _section(
            "Educacion", "\n".join(edu_blocks)) if edu_blocks else "",
    }
    for key, value in mapping.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def job_cv_dir(job_id: int) -> Path:
    path = CVS_DIR / f"job_{job_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compile_pdf(tex_path: Path) -> Path | None:
    """Compila con pdflatex si existe; None si no hay compilador."""
    compiler = shutil.which("pdflatex")
    if not compiler:
        logger.info("pdflatex no instalado: se entrega solo .tex")
        return None
    try:
        subprocess.run(
            [compiler, "-interaction=nonstopmode", "-halt-on-error",
             tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            timeout=120,
            check=True,
        )
    except (subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as error:
        logger.warning("pdflatex fallo: %s", error)
        return None
    pdf = tex_path.with_suffix(".pdf")
    return pdf if pdf.exists() else None


def generate_for_job(
    job_id: int,
    content: CVContent,
    personal: dict,
    analysis: dict | None = None,
) -> dict:
    """Escribe analysis.json + cv_content.json + cv.tex (+ cv.pdf si se
    puede compilar). Devuelve rutas y flags honestos."""
    directory = job_cv_dir(job_id)
    (directory / "cv_content.json").write_text(
        json.dumps(content.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if analysis is not None:
        (directory / "analysis.json").write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    tex_path = directory / "cv.tex"
    tex_path.write_text(render_tex(content, personal), encoding="utf-8")
    pdf_path = compile_pdf(tex_path)
    return {
        "dir": str(directory),
        "tex_path": str(tex_path),
        "pdf_path": str(pdf_path) if pdf_path else None,
        "pdf_ok": pdf_path is not None,
    }
