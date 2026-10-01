#!/usr/bin/env bash
# Build del backend en Render (pone en codigo lo que antes iba en el
# dashboard, donde los comandos largos dan errores).
#
# Uso por unica vez en Render (Settings -> Build Command):
#   bash backend/build.sh
# (Si tu Root Directory ya es `backend`, usa: bash build.sh)
#
# Hace dos cosas que requirements.txt NO puede hacer solo:
#  1. pip install (libreria playwright, ~40MB).
#  2. Descargar el navegador Chromium (~115MB, binario aparte que pip
#     no distribuye: por eso existe `playwright install`).
set -o errexit

if [ -f backend/requirements.txt ]; then
  REQ="backend/requirements.txt"
elif [ -f requirements.txt ]; then
  REQ="requirements.txt"
else
  echo "ERROR: no se encontro requirements.txt" >&2
  exit 1
fi

echo "==> pip install -r $REQ"
pip install -r "$REQ"

echo "==> playwright install chromium --only-shell"
python -m playwright install chromium --only-shell

echo "==> Build OK: dependencias + Chromium listos"
