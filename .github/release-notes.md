# STL2STEP FC @VERSION@

Splash screen and a much faster startup.

## Downloads

### Windows 11 / x86_64

| File | Description |
| --- | --- |
| `STL2STEP-FC-@VERSION@-Windows-x86_64-Setup.exe` | Installer (per-user, no administrator rights required) |
| `STL2STEP-FC-@VERSION@-Windows-x86_64-Portable.zip` | Portable version, extract and run |

The installer is not code-signed, so Windows SmartScreen may ask for confirmation
("More info" → "Run anyway"). For the portable version, extract the whole ZIP
before launching `STL2STEP.exe`.

### Linux / x86_64

```bash
wget https://github.com/FSMaker77/STL2STEP-FC/releases/download/v@VERSION@/STL2STEP-FC-@VERSION@-Linux-x86_64.AppImage
chmod +x STL2STEP-FC-@VERSION@-Linux-x86_64.AppImage
./STL2STEP-FC-@VERSION@-Linux-x86_64.AppImage
```

If FUSE is not available, run it with `--appimage-extract-and-run`.

## What's new in @VERSION@

- **New splash screen** on Windows and Linux.
- **Much faster startup**: the CAD engine (OpenCASCADE) and SciPy are now loaded
  on the first conversion instead of at application launch. The GUI opens in a
  fraction of a second on subsequent starts; the first launch is still bounded
  by the antivirus scanning the newly installed files.
- **Precompiled bytecode**: the Windows build ships `.pyc` files (or generates
  them once during installation) to avoid the first-run compilation cost.
- Linux AppImage build now also works in environments without FUSE at build time.

## Italiano

### Download

- **Windows 11 x86_64**: `STL2STEP-FC-@VERSION@-Windows-x86_64-Setup.exe`
  (installer per l'utente corrente, senza diritti di amministratore) oppure
  `STL2STEP-FC-@VERSION@-Windows-x86_64-Portable.zip` (estrarre tutto e avviare
  `STL2STEP.exe`).
- **Linux x86_64**: `STL2STEP-FC-@VERSION@-Linux-x86_64.AppImage`
  (`chmod +x` e avvio; con FUSE assente usare `--appimage-extract-and-run`).

### Novità della @VERSION@

- **Nuova splash screen** su Windows e Linux.
- **Avvio molto più rapido**: il motore CAD (OpenCASCADE) e SciPy vengono
  caricati alla prima conversione, non all'avvio. Dalla seconda apertura la GUI
  è pronta in una frazione di secondo; il primo avvio resta influenzato
  dall'analisi antivirus dei file appena installati.
- **Bytecode precompilato** nella build Windows per eliminare il costo di
  compilazione al primo avvio.

## Checksums

Ogni file ha il proprio `.sha256`; l'elenco completo è in `SHA256SUMS.txt`.
