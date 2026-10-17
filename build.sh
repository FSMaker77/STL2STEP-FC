#!/usr/bin/env bash
# STL2STEP — build script: creates a virtualenv and installs dependencies.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

echo "==> STL2STEP build"
echo "==> Python: $($PYTHON --version 2>&1)"

if [ ! -d ".venv" ]; then
    echo "==> Creazione virtualenv (.venv)"
    "$PYTHON" -m venv .venv
fi

echo "==> Aggiornamento pip"
./.venv/bin/python -m pip install --upgrade pip -q

echo "==> Installazione dipendenze (può richiedere qualche minuto)"
./.venv/bin/python -m pip install -r requirements.txt

echo "==> Installazione del pacchetto in modalità sviluppo"
./.venv/bin/python -m pip install -e .

echo
echo "Fatto! Avvia la GUI con:  ./run.sh"
echo "Oppure la CLI con:        ./.venv/bin/stl2step --help"
