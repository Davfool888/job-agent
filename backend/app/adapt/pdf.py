"""HTML -> PDF con Chromium headless via Playwright (FASE 7).

Servicio independiente: recibe HTML, devuelve un PDF A4 verificado.
JavaScript apagado (el CV no lo necesita) y sin recursos externos.
"""
from __future__ import annotations

from pathlib import Path


class PdfError(RuntimeError):
    """Error controlado con codigo para la API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as runner:
            browser = runner.chromium.launch(args=["--no-sandbox"])
            browser.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def html_to_pdf(
    html_text: str, out_path: str | Path, timeout_ms: int = 60000
) -> Path:
    """Convierte HTML a PDF A4. Lanza PdfError con codigo."""
    from app.config import ADAPT_PDF_TIMEOUT_MS

    out = Path(out_path)
    if not str(html_text or "").strip():
        raise PdfError("PDF_EMPTY_HTML", "HTML vacio, nada que convertir.")
    timeout = int(timeout_ms or ADAPT_PDF_TIMEOUT_MS)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PdfError(
            "PDF_BROWSER_MISSING",
            "Motor PDF no instalado (playwright + chromium).",
        ) from error
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page(java_script_enabled=False)
                page.set_content(html_text, wait_until="load",
                                 timeout=timeout)
                page.pdf(
                    path=str(out),
                    format="A4",
                    print_background=True,
                    prefer_css_page_size=False,
                    margin={"top": "16mm", "bottom": "16mm",
                            "left": "15mm", "right": "15mm"},
                )
            finally:
                browser.close()
    except PdfError:
        raise
    except Exception as error:  # noqa: BLE001
        message = str(error)
        if "Timeout" in type(error).__name__ or "timeout" in message.lower():
            raise PdfError(
                "PDF_TIMEOUT",
                "La generacion del PDF excedio el tiempo limite.",
            ) from error
        raise PdfError(
            "PDF_GENERATION_FAILED",
            f"No fue posible generar el PDF: {message[:200]}",
        ) from error
    if not out.exists() or out.stat().st_size == 0:
        raise PdfError("PDF_EMPTY_FILE", "El PDF generado esta vacio.")
    with open(out, "rb") as handler:
        if handler.read(5) != b"%PDF-":
            raise PdfError(
                "PDF_INVALID_FILE", "El archivo generado no es un PDF.")
    return out
