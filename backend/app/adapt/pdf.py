"""HTML -> PDF con Chromium headless via Playwright (FASE 7).

Servicio independiente: recibe HTML, devuelve un PDF A4 verificado.
JavaScript apagado (el CV no lo necesita) y sin recursos externos.

Si Chromium no esta instalado (servidor nuevo), se dispara su
instalacion en segundo plano y se devuelve BROWSER_MISSING con
instrucciones; el siguiente intento ya funciona.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path


class PdfError(RuntimeError):
    """Error controlado con codigo para la API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_install_lock = threading.Lock()
_installing = False

# Serializa generaciones: dos Chromium a la vez tumban instancias
# chicas (OOM en plan gratuito). El segundo espera su turno.
_pdf_lock = threading.Lock()
PDF_LOCK_TIMEOUT = 180


def _executable_missing(message: str) -> bool:
    return "Executable doesn't exist" in (message or "")


def _trigger_background_install() -> None:
    """Descarga Chromium sin bloquear el request (una sola vez)."""
    global _installing
    with _install_lock:
        if _installing:
            return
        _installing = True

    def _run() -> None:
        global _installing
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install",
                 "chromium", "--only-shell"],
                timeout=600, check=False, capture_output=True,
            )
        except Exception:  # noqa: BLE001
            pass
        finally:
            with _install_lock:
                _installing = False

    threading.Thread(target=_run, daemon=True).start()


def _browser_present() -> bool:
    """True si el ejecutable existe (sin lanzar nada: 0 RAM)."""
    try:
        import os

        from playwright.sync_api import sync_playwright

        with sync_playwright() as runner:
            path = runner.chromium.executable_path
        return bool(path) and os.path.exists(path)
    except Exception:  # noqa: BLE001
        return False


def warmup_chromium() -> bool:
    """Asegura Chromium al arrancar sin picos de memoria: solo verifica
    el archivo y, si falta, instala en fondo. Nunca lanza el navegador
    (en 512MB un launch en boot puede tumbar el arranque)."""
    try:
        if _browser_present():
            return True
    except Exception:  # noqa: BLE001
        pass
    _trigger_background_install()
    return False


def chromium_available() -> bool:
    """Solo verifica presencia (sin lanzar: apto para chequeos baratos)."""
    return _browser_present()


def html_to_pdf(
    html_text: str, out_path: str | Path, timeout_ms: int = 60000
) -> Path:
    """Convierte HTML a PDF A4. Lanza PdfError con codigo."""
    from app.config import ADAPT_PDF_TIMEOUT_MS

    out = Path(out_path)
    if not str(html_text or "").strip():
        raise PdfError("PDF_EMPTY_HTML", "HTML vacio, nada que convertir.")
    try:
        timeout = int(
            timeout_ms if timeout_ms is not None else ADAPT_PDF_TIMEOUT_MS)
    except (TypeError, ValueError):
        # Frontera defensiva: un tipo inesperado jamas debe tumbar
        # la generacion con TypeError crudo (bug int(dict) historico).
        timeout = ADAPT_PDF_TIMEOUT_MS
    if not _pdf_lock.acquire(timeout=PDF_LOCK_TIMEOUT):
        raise PdfError(
            "PDF_BUSY",
            "Servidor ocupado generando otro PDF, reintenta en 1 minuto.",
        )
    try:
        return _render_locked(html_text, out, timeout)
    finally:
        _pdf_lock.release()


def _render_locked(html_text: str, out: Path, timeout: int) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PdfError(
            "PDF_BROWSER_MISSING",
            "Motor PDF no instalado (playwright + chromium).",
        ) from error
    try:
        with sync_playwright() as runner:
            # Flags de bajo consumo: contenedores sin privilegios,
            # /dev/shm diminuto y poca RAM (plan gratuito).
            browser = runner.chromium.launch(args=[
                "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--no-zygote", "--single-process"])
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
        if _executable_missing(message):
            _trigger_background_install()
            raise PdfError(
                "BROWSER_MISSING",
                "Motor PDF ausente en el servidor: instalacion iniciada, "
                "reintenta en 2 minutos. (Permanente: agrega "
                "'playwright install chromium --only-shell' al build).",
            ) from error
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
