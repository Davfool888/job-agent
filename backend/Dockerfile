# Dockerfile para Render - Job Agent Backend
# Incluye: Python 3.11 + TeX Live (pdflatex) + Playwright Chromium

FROM python:3.11-slim-bookworm

# Evita prompts interactivos durante la instalación
ENV DEBIAN_FRONTEND=noninteractive

# Instala dependencias del sistema + TeX Live (pdflatex) + Playwright deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    # TeX Live mínimo para pdflatex (esquema small ~200MB)
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-lang-spanish \
    # Playwright / Chromium dependencias
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    # Utilidades
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copia requirements e instala dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala Chromium para Playwright (solo binarios, sin navegador completo)
# Usamos la variable de entorno para cachear en /ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium --only-shell

# Copia el código de la aplicación
COPY . .

# Crea directorios de datos (persistentes en Render Disk si se configura)
RUN mkdir -p /app/data/cvs /app/data/profiles /app/data/profile_cvs /app/data/adapt_cvs

# Expone el puerto
EXPOSE 8000

# Variables de entorno por defecto (sobrescribir en Render Dashboard)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Comando de inicio
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]