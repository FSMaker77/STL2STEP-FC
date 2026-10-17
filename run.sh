#!/usr/bin/env bash
# STL2STEP — launch the GUI (builds the venv on first run if needed).
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "Ambiente non trovato, eseguo build.sh..."
    ./build.sh
fi

exec ./.venv/bin/python -m stl2step "$@"
