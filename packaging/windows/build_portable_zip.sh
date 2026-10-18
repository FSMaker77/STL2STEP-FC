#!/usr/bin/env bash
# Build the portable Windows x86_64 ZIP from an already prepared payload.
# Run ./packaging/windows/build_windows.sh first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/packaging/windows"
BUILD="$ROOT/dist/win-build"
PAYLOAD="$BUILD/payload"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/stl2step/version.py")"
NAME="STL2STEP-FC-${VERSION}-Windows-x86_64-Portable"
STAGE="$ROOT/dist/portable-stage"
OUTFILE="$ROOT/dist/${NAME}.zip"

die() { echo "ERRORE: $*" >&2; exit 1; }

[ -n "$VERSION" ] || die "versione non trovata in stl2step/version.py"
[ -d "$PAYLOAD" ] || die "payload non trovato: esegui prima build_windows.sh"
[ -f "$HERE/LEGGIMI-portable.txt" ] || die "LEGGIMI-portable.txt mancante"

echo "==> Creazione pacchetto portabile"
rm -rf "$STAGE"
mkdir -p "$STAGE/$NAME"
cp -a "$PAYLOAD/." "$STAGE/$NAME/"
cp "$HERE/LEGGIMI-portable.txt" "$STAGE/$NAME/LEGGIMI.txt"

rm -f "$OUTFILE"
( cd "$STAGE" && zip -r -6 "$OUTFILE" "$NAME" )
( cd "$ROOT/dist" && sha256sum "$(basename "$OUTFILE")" > "$(basename "$OUTFILE").sha256" )
rm -rf "$STAGE"

echo
echo "Pacchetto portabile creato: $OUTFILE"
ls -lh "$OUTFILE"
