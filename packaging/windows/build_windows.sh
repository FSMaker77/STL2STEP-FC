#!/usr/bin/env bash
# Build the Windows 11 x86_64 installer of STL2STEP FC from Linux.
#
# The result is a normal NSIS setup (per-user install), not a single huge
# PyInstaller executable: the bundled CPython runtime and dependencies are
# installed as ordinary files, so they can be updated/removed cleanly.
#
# Requirements on the build host:
#   - python3 + pip (to download win_amd64 wheels)
#   - curl, unzip
#   - makensis (NSIS 3.x)
#   - x86_64-w64-mingw32-gcc / -windres (MinGW-w64)
#   - ImageMagick `convert` (only to generate the .ico if missing)
#
# Output: dist/STL2STEP-FC-<version>-Windows-x86_64-Setup.exe
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/packaging/windows"
BUILD="$ROOT/dist/win-build"
CACHE="$BUILD/cache"
WHEELS="$BUILD/wheels"
PAYLOAD="$BUILD/payload"
EXTRAS="$BUILD/extras"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/stl2step/version.py")"
OUTFILE="$ROOT/dist/STL2STEP-FC-${VERSION}-Windows-x86_64-Setup.exe"

PYVER="3.12.10"
PYTAG="312"
PYZIP="$CACHE/python-${PYVER}-embed-amd64.zip"
PYURL="https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-embed-amd64.zip"

# Pinned to the versions used by the Linux build (see pyproject.toml).
NUMPY="2.5.4"
SCIPY="1.18.1"
PYSIDE="6.12.0"
SHIBOKEN="6.12.0"
OCP="8.0.1.1.0"
VTK="9.6.2"

# Transitive DLL closure of OCP's TKIVtk (VTK 9.6.2), plus the VTK Python
# wrapping core imported directly by OCP.cp312-win_amd64.pyd. Only the DLLs
# are installed; the vtkmodules Python package is not needed by STL2STEP.
VTK_DLLS=(
    msvcp140-ba05f997e25eac0cb10acfddf6513d26.dll
    vtkCommonColor-9.6.2.dll
    vtkCommonComputationalGeometry-9.6.2.dll
    vtkCommonCore-9.6.2.dll
    vtkCommonDataModel-9.6.2.dll
    vtkCommonExecutionModel-9.6.2.dll
    vtkCommonMath-9.6.2.dll
    vtkCommonMisc-9.6.2.dll
    vtkCommonSystem-9.6.2.dll
    vtkCommonTransforms-9.6.2.dll
    vtkDICOMParser-9.6.2.dll
    vtkFiltersCore-9.6.2.dll
    vtkFiltersGeneral-9.6.2.dll
    vtkFiltersGeometry-9.6.2.dll
    vtkFiltersHybrid-9.6.2.dll
    vtkFiltersHyperTree-9.6.2.dll
    vtkFiltersReduction-9.6.2.dll
    vtkFiltersSources-9.6.2.dll
    vtkFiltersVerdict-9.6.2.dll
    vtkIOCore-9.6.2.dll
    vtkIOImage-9.6.2.dll
    vtkImagingCore-9.6.2.dll
    vtkImagingSources-9.6.2.dll
    vtkInteractionStyle-9.6.2.dll
    vtkRenderingCore-9.6.2.dll
    vtkRenderingFreeType-9.6.2.dll
    vtkRenderingHyperTreeGrid-9.6.2.dll
    vtkRenderingOpenGL2-9.6.2.dll
    vtkRenderingUI-9.6.2.dll
    vtkWrappingPythonCore3.12-9.6.2.dll
    vtkfmt-9.6.2.dll
    vtkfreetype-9.6.2.dll
    vtkglad-9.6.2.dll
    vtkjpeg-9.6.2.dll
    vtkkissfft-9.6.2.dll
    vtkloguru-9.6.2.dll
    vtklz4-9.6.2.dll
    vtklzma-9.6.2.dll
    vtkmetaio-9.6.2.dll
    vtkpng-9.6.2.dll
    vtkpugixml-9.6.2.dll
    vtkscn-9.6.2.dll
    vtksys-9.6.2.dll
    vtktiff-9.6.2.dll
    vtktoken-9.6.2.dll
    vtkverdict-9.6.2.dll
    vtkzlib-9.6.2.dll
)

die() { echo "ERRORE: $*" >&2; exit 1; }

for tool in python3 curl unzip makensis x86_64-w64-mingw32-gcc x86_64-w64-mingw32-windres; do
    command -v "$tool" >/dev/null 2>&1 || die "strumento mancante: $tool"
done
[ -n "$VERSION" ] || die "versione non trovata in stl2step/version.py"

mkdir -p "$CACHE" "$WHEELS" "$ROOT/dist"

have_wheel() {
    compgen -G "$WHEELS/$1" >/dev/null 2>&1
}

if ! have_wheel "numpy-${NUMPY}-cp312-cp312-win_amd64.whl" \
   || ! have_wheel "scipy-${SCIPY}-cp312-cp312-win_amd64.whl" \
   || ! have_wheel "pyside6_essentials-${PYSIDE}-cp310-abi3-win_amd64.whl" \
   || ! have_wheel "shiboken6-${SHIBOKEN}-cp310-abi3-win_amd64.whl" \
   || ! have_wheel "cadquery_ocp-${OCP}-cp312-cp312-win_amd64.whl" \
   || ! have_wheel "vtk-${VTK}-cp312-cp312-win_amd64.whl"; then
    echo "==> Download wheel Windows x86_64"
    python3 -m pip download \
        --only-binary=:all: \
        --platform win_amd64 \
        --python-version "$PYTAG" \
        --implementation cp \
        --abi "cp${PYTAG}" \
        --no-deps \
        --dest "$WHEELS" \
        "numpy==${NUMPY}" \
        "scipy==${SCIPY}" \
        "PySide6_Essentials==${PYSIDE}" \
        "shiboken6==${SHIBOKEN}" \
        "cadquery-ocp==${OCP}" \
        "vtk==${VTK}"
fi

if [ ! -f "$PYZIP" ]; then
    echo "==> Download Python ${PYVER} embeddable"
    curl -fL --retry 3 -o "$PYZIP" "$PYURL"
fi
unzip -tq "$PYZIP" >/dev/null

echo "==> Preparazione payload"
rm -rf "$PAYLOAD" "$BUILD/vtk-unpacked" "$BUILD/pyside-keep" "$BUILD/launcher.o"
mkdir -p "$PAYLOAD/Lib/site-packages" "$EXTRAS/samples"

unzip -q "$PYZIP" -d "$PAYLOAD"
printf 'python%s.zip\n.\nLib\\site-packages\nimport site\n' "$PYTAG" > "$PAYLOAD/python${PYTAG}._pth"

[ -f "$PAYLOAD/python.exe" ] || die "python.exe non trovato nel runtime embeddable"
[ -f "$PAYLOAD/python${PYTAG}.dll" ] || die "python${PYTAG}.dll non trovato nel runtime embeddable"

unzip -q -o "$WHEELS/numpy-"*.whl       -d "$PAYLOAD/Lib/site-packages"
unzip -q -o "$WHEELS/scipy-"*.whl       -d "$PAYLOAD/Lib/site-packages"
unzip -q -o "$WHEELS/cadquery_ocp-"*.whl -d "$PAYLOAD/Lib/site-packages"
unzip -q -o "$WHEELS/pyside6_essentials-"*.whl -d "$PAYLOAD/Lib/site-packages"
unzip -q -o "$WHEELS/shiboken6-"*.whl   -d "$PAYLOAD/Lib/site-packages"
unzip -q -o "$WHEELS/vtk-"*.whl         -d "$BUILD/vtk-unpacked"

# Some wheels contain a zero-byte self-name placeholder; never install wheels.
rm -f "$PAYLOAD/Lib/site-packages/"*.whl

echo "==> Copia DLL VTK richieste da OCP/TKIVtk"
mkdir -p "$PAYLOAD/Lib/site-packages/vtk.libs"
for dll in "${VTK_DLLS[@]}"; do
    src="$BUILD/vtk-unpacked/vtk.libs/$dll"
    [ -f "$src" ] || die "DLL VTK mancante: $dll"
    cp "$src" "$PAYLOAD/Lib/site-packages/vtk.libs/"
done
rm -rf "$BUILD/vtk-unpacked"

echo "==> Riduzione PySide6 ai soli moduli usati"
PS="$PAYLOAD/Lib/site-packages/PySide6"
KEEP="$BUILD/pyside-keep"
rm -rf "$KEEP"
mkdir -p "$KEEP/plugins/platforms" "$KEEP/plugins/styles" "$KEEP/plugins/imageformats" "$KEEP/resources"
for f in \
    __init__.py _config.py _git_pyside_version.py pyside6.abi3.dll \
    QtCore.pyd QtGui.pyd QtWidgets.pyd QtOpenGL.pyd QtOpenGLWidgets.pyd \
    Qt6Core.dll Qt6Gui.dll Qt6Widgets.dll Qt6OpenGL.dll Qt6OpenGLWidgets.dll \
    opengl32sw.dll concrt140.dll msvcp140.dll msvcp140_1.dll msvcp140_2.dll \
    msvcp140_codecvt_ids.dll vcruntime140.dll vcruntime140_1.dll; do
    [ -f "$PS/$f" ] || die "file PySide6 mancante: $f"
    cp "$PS/$f" "$KEEP/"
done
cp "$PS/resources/icudtl.dat" "$KEEP/resources/"
cp "$PS/plugins/platforms/qwindows.dll" "$KEEP/plugins/platforms/"
cp "$PS/plugins/styles/qmodernwindowsstyle.dll" "$KEEP/plugins/styles/"
cp "$PS/plugins/imageformats/qico.dll" "$KEEP/plugins/imageformats/"
rm -rf "$PS"
mv "$KEEP" "$PS"

echo "==> Riduzione shiboken6"
SH="$PAYLOAD/Lib/site-packages/shiboken6"
rm -f "$SH"/*.pyi "$SH"/*.lib
rm -rf "$SH/include" "$SH/lib" "$SH/py.typed"
rm -rf "$PAYLOAD/Lib/site-packages/PySide6_Essentials-"*.dist-info
rm -rf "$PAYLOAD/Lib/site-packages/shiboken6-"*.dist-info

echo "==> Pulizia metadati inutili"
rm -rf "$PAYLOAD/Lib/site-packages/cadquery_ocp"
rm -rf "$PAYLOAD/Lib/site-packages/cadquery_ocp-"*.dist-info
find "$PAYLOAD/Lib/site-packages/numpy" "$PAYLOAD/Lib/site-packages/scipy" \
    -type d -name tests -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> Copia applicazione"
cp -r "$ROOT/stl2step" "$PAYLOAD/Lib/site-packages/"
cp "$HERE/diagnostica.bat" "$HERE/diagnostica_dll.py" "$PAYLOAD/"
PEFILE="$(python3 -c 'import pefile; print(pefile.__file__)' 2>/dev/null || true)"
if [ -n "$PEFILE" ] && [ -f "$PEFILE" ]; then
    cp "$PEFILE" "$PAYLOAD/"
fi
echo "==> Pulizia cache Python"
find "$PAYLOAD" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$PAYLOAD" -name '*.pyc' -delete

# Precompila il bytecode con un interprete della stessa minor version del
# runtime (3.12).  I .pyc evitano di compilare ~400 moduli al primo avvio.
# Su host Linux/CI impostare PYC_PYTHON=/percorso/python3.12; se non c'e',
# i .pyc vengono creati da NSIS all'installazione (installer) o al primo
# avvio (portable).
PYC_PYTHON="${PYC_PYTHON:-}"
if [ -z "$PYC_PYTHON" ] && command -v "python${PYTAG}" >/dev/null 2>&1; then
    PYC_PYTHON="python${PYTAG}"
fi
PY_MAJOR="${PYTAG:0:1}"
PY_MINOR="${PYTAG:1}"
if [ -n "$PYC_PYTHON" ] \
   && "$PYC_PYTHON" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (${PY_MAJOR}, ${PY_MINOR}) else 1)"; then
    echo "==> Precompilazione bytecode con $("$PYC_PYTHON" -V 2>&1)"
    "$PYC_PYTHON" -m compileall --invalidation-mode checked-hash -q -j 0 \
        "$PAYLOAD/Lib/site-packages" >/dev/null \
        || echo "ATTENZIONE: precompilazione parziale (i moduli mancanti saranno compilati al primo avvio)"
else
    echo "==> Python ${PY_MAJOR}.${PY_MINOR} non trovato: nessun .pyc nel payload"
fi

echo "==> Copia runtime MSVC accanto a python.exe"
for f in concrt140.dll msvcp140.dll msvcp140_1.dll msvcp140_2.dll \
         msvcp140_codecvt_ids.dll vcruntime140.dll vcruntime140_1.dll; do
    [ -f "$PS/$f" ] && cp -f "$PS/$f" "$PAYLOAD/$f"
done
[ -f "$PAYLOAD/python3.dll" ] || die "python3.dll mancante"

# Windows resolves an extension module's dependencies relative to the module
# directory first. Keep every OCP/VTK runtime DLL next to OCP.cp312-win_amd64.pyd
# instead of relying on AddDllDirectory and cross-directory lookup.
echo "==> Consolidamento DLL OCP/VTK nella directory OCP"
OCPDIR="$PAYLOAD/Lib/site-packages/OCP"
for d in "$PAYLOAD/Lib/site-packages/cadquery_ocp.libs" \
         "$PAYLOAD/Lib/site-packages/vtk.libs"; do
    if [ -d "$d" ]; then
        find "$d" -maxdepth 1 -type f -name '*.dll' -exec mv -f {} "$OCPDIR/" \;
    fi
done
for f in vcruntime140.dll vcruntime140_1.dll python312.dll; do
    cp -f "$PAYLOAD/$f" "$OCPDIR/"
done

echo "==> Icona"
ICON="$HERE/stl2step.ico"
if [ ! -f "$ICON" ]; then
    command -v convert >/dev/null 2>&1 || die "ImageMagick convert non trovato"
    convert -background none "$ROOT/packaging/stl2step.svg" \
        -define icon:auto-resize=256,128,64,48,32,16 "$ICON"
fi

echo "==> Compilazione launcher Windows"
VERSION_COMMA="${VERSION//./,}"
RC="$BUILD/launcher.rc"
sed -e "s|@ICON@|$ICON|g" \
    -e "s|@VERSION_COMMA@|$VERSION_COMMA|g" \
    -e "s|@VERSION@|$VERSION|g" \
    "$HERE/launcher.rc.in" > "$RC"
x86_64-w64-mingw32-windres "$RC" -O coff -o "$BUILD/launcher.o"
x86_64-w64-mingw32-gcc -O2 -municode -mwindows -DGUI=1 \
    "$HERE/launcher.c" "$BUILD/launcher.o" -o "$PAYLOAD/STL2STEP.exe" -static
x86_64-w64-mingw32-gcc -O2 -municode -mconsole -DGUI=0 \
    "$HERE/launcher.c" "$BUILD/launcher.o" -o "$PAYLOAD/stl2step-cli.exe" -static

cp "$HERE/stl2step_gui.pyw" "$PAYLOAD/stl2step_gui.pyw"
printf '@echo off\r\n"%%~dp0python.exe" -m stl2step.cli %%*\r\n' > "$PAYLOAD/stl2step.cmd"

echo "==> Extra (licenza, README, campioni)"
cp "$ROOT/LICENSE" "$ROOT/README.md" "$EXTRAS/"
cp "$ROOT/samples"/*.stl "$EXTRAS/samples/"

echo "==> Creazione setup NSIS"
rm -f "$OUTFILE"
( cd "$HERE" && makensis -V2 \
    -DVERSION="$VERSION" \
    -DPAYLOAD="$PAYLOAD" \
    -DEXTRAS="$EXTRAS" \
    -DOUTFILE="$OUTFILE" \
    installer.nsi )

( cd "$ROOT/dist" && sha256sum "$(basename "$OUTFILE")" > "$(basename "$OUTFILE").sha256" )
find "$PAYLOAD" -type f -printf '%s %P\n' | sort -k2 > "$BUILD/payload-manifest.txt"

echo
echo "Setup creato: $OUTFILE"
ls -lh "$OUTFILE"
echo "Dimensione payload installato: $(du -sh "$PAYLOAD" | cut -f1)"
