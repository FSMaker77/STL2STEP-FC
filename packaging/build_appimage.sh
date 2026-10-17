#!/usr/bin/env bash
# Build a self-contained AppImage for STL2STEP.
#
# Requirements:
#   - a working environment (run ./build.sh first)
#   - network access (to download appimagetool)
#   - FUSE is NOT required at build time; it is only needed to *run* the AppImage
#     on some distributions (or use `./STL2STEP.AppImage --appimage-extract-and-run`).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
    echo "Ambiente non trovato: esegui prima ./build.sh" >&2
    exit 1
fi

APP="STL2STEP-FC"
VERSION="$(./.venv/bin/python -c 'import stl2step; print(stl2step.__version__)')"
PYVER="$(./.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

APPDIR="$ROOT/dist/AppDir"
OUT="$ROOT/dist/${APP}-${VERSION}-Linux-x86_64.AppImage"

echo "==> Costruzione AppDir per ${APP} ${VERSION} (Python ${PYVER})"

rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/lib" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# --- Python runtime ---------------------------------------------------------
# The venv python is a symlink to the system binary; resolve it and bundle the
# real executable together with its shared library.
PYBIN="$(readlink -f .venv/bin/python)"
cp -P "$PYBIN" "$APPDIR/usr/bin/python3"

SYS_LIBDIR="$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')"
for lib in libpython${PYVER}.so*; do
    [ -e "$SYS_LIBDIR/$lib" ] && cp -P "$SYS_LIBDIR/$lib" "$APPDIR/usr/lib/"
done

# Standard library
STDLIB="$(./.venv/bin/python -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
mkdir -p "$APPDIR/usr/lib/python${PYVER}"
cp -r "$STDLIB/." "$APPDIR/usr/lib/python${PYVER}/"

# Site-packages (numpy, scipy, PySide6, OCP, VTK, ...)
SITEPKG="$(./.venv/bin/python -c 'import site; print(site.getsitepackages()[0])')"
cp -r "$SITEPKG/." "$APPDIR/usr/lib/python${PYVER}/site-packages/"

# The application package itself (editable install already put it on the path,
# but copy the source tree explicitly so it is definitely present)
mkdir -p "$APPDIR/usr/lib/python${PYVER}/site-packages/stl2step"
cp -r stl2step/. "$APPDIR/usr/lib/python${PYVER}/site-packages/stl2step/"

# --- AppRun / desktop / icon ------------------------------------------------
cp packaging/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp packaging/stl2step.desktop "$APPDIR/stl2step.desktop"
cp packaging/stl2step.desktop "$APPDIR/usr/share/applications/stl2step.desktop"

if command -v convert >/dev/null 2>&1; then
    convert -background none packaging/stl2step.svg "$APPDIR/usr/share/icons/hicolor/256x256/apps/stl2step.png" 2>/dev/null || \
    cp packaging/stl2step.svg "$APPDIR/stl2step.svg"
fi
# appimagetool accepts an SVG as icon as a fallback
cp packaging/stl2step.svg "$APPDIR/stl2step.svg"

# --- appimagetool -----------------------------------------------------------
TOOL_DIR="$ROOT/dist/tools"
mkdir -p "$TOOL_DIR"
APPIMAGETOOL="$TOOL_DIR/appimagetool"
if [ ! -x "$APPIMAGETOOL" ]; then
    echo "==> Scarico appimagetool"
    URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    curl -fL --retry 3 -o "$APPIMAGETOOL" "$URL" || wget -O "$APPIMAGETOOL" "$URL"
    chmod +x "$APPIMAGETOOL"
fi

echo "==> Generazione ${OUT}"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$OUT"

echo
echo "AppImage creato: $OUT"
echo "Eseguilo con:     ./$OUT   (o ./$OUT --appimage-extract-and-run se FUSE non è disponibile)"
