"""Report why OCP (or another extension module) cannot be loaded on Windows.

Run from the portable folder with: diagnostica.bat
"""

from __future__ import annotations

import ctypes
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "Lib", "site-packages")
OCP = os.path.join(SITE, "OCP")
OCP_PYD = os.path.join(OCP, "OCP.cp312-win_amd64.pyd")

SYSTEM_DLLS = {
    "kernel32.dll", "user32.dll", "advapi32.dll", "ws2_32.dll", "wsock32.dll",
    "shell32.dll", "ole32.dll", "oleaut32.dll", "gdi32.dll", "comctl32.dll",
    "comdlg32.dll", "winmm.dll", "imm32.dll", "rpcrt4.dll", "netapi32.dll",
    "userenv.dll", "mpr.dll", "dnsapi.dll", "iphlpapi.dll", "bcrypt.dll",
    "secur32.dll", "crypt32.dll", "psapi.dll", "version.dll", "setupapi.dll",
    "cfgmgr32.dll", "dwmapi.dll", "uxtheme.dll", "d3d11.dll", "dxgi.dll",
    "opengl32.dll", "glu32.dll", "dwrite.dll", "d3dcompiler_47.dll",
    "msimg32.dll", "winspool.drv", "usp10.dll", "shlwapi.dll", "urlmon.dll",
    "wininet.dll", "winhttp.dll", "dbghelp.dll", "powrprof.dll", "pdh.dll",
    "wtsapi32.dll", "msvcrt.dll", "ntdll.dll", "wldapi.dll", "dsrole.dll",
    "logoncli.dll", "samcli.dll", "netutils.dll", "srvcli.dll", "wkssvc.dll",
    "ntdsapi.dll", "authz.dll", "cryptbase.dll", "ncrypt.dll",
    "bcryptprimitives.dll", "sspicli.dll", "profapi.dll", "kernelbase.dll",
    "apphelp.dll", "msvcp_win.dll", "ucrtbase.dll", "sechost.dll",
    "combase.dll", "winsta.dll", "dcomp.dll", "windowscodecs.dll",
    "propsys.dll", "oleacc.dll", "mfuuid.dll", "mfplat.dll", "mf.dll",
    "evr.dll", "avrt.dll", "d2d1.dll", "d3d9.dll", "d3d12.dll", "dxcore.dll",
    "mscoree.dll", "mshtml.dll", "imagehlp.dll", "wintrust.dll",
    "mswsock.dll", "rsaenh.dll", "gpapi.dll", "dpapi.dll", "cryptsp.dll",
    "ntmarta.dll", "wevtapi.dll",
}

SEARCH_DIRS = [
    ROOT,
    SITE,
    OCP,
    os.path.join(SITE, "cadquery_ocp.libs"),
    os.path.join(SITE, "vtk.libs"),
    os.path.join(SITE, "PySide6"),
    os.path.join(SITE, "shiboken6"),
    os.path.join(SITE, "numpy.libs"),
    os.path.join(SITE, "scipy.libs"),
]


def say(*args: object) -> None:
    print(*args)


def index_files() -> dict[str, str]:
    index: dict[str, str] = {}
    for directory in SEARCH_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                index.setdefault(name.lower(), path)
    return index


def pe_imports(path: str) -> list[str]:
    import struct

    import pefile  # bundled next to this script

    pe = pefile.PE(path, fast_load=True)
    names: list[str] = []

    # Read the import descriptor table directly: pefile can stop early on
    # some wheels with very large import tables.
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[1]
    if directory.VirtualAddress and directory.Size:
        try:
            raw = pe.get_data(directory.VirtualAddress, directory.Size)
            for offset in range(0, len(raw), 20):
                entry = raw[offset:offset + 20]
                if len(entry) < 20:
                    break
                oft, stamp, chain, name_rva, first_thunk = struct.unpack(
                    "<IIIII", entry
                )
                if not any((oft, stamp, chain, name_rva, first_thunk)):
                    break
                names.append(pe.get_string_at_rva(name_rva).decode("latin1"))
        except Exception:
            pass

    # Delay imports are not part of the normal descriptor table.
    try:
        pe.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY[
                    "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"
                ],
            ]
        )
    except Exception:
        pass
    for entry in getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", []) or []:
        if entry.dll:
            names.append(entry.dll.decode("latin1"))

    return names


def walk(start: str, index: dict[str, str]) -> tuple[int, list[tuple[str, str]]]:
    seen: set[str] = set()
    missing: list[tuple[str, str]] = []
    todo = [start]
    while todo:
        path = todo.pop()
        key = os.path.abspath(path).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            names = pe_imports(path)
        except Exception as exc:  # noqa: BLE001
            missing.append((f"<cannot parse: {exc}>", path))
            continue
        for name in names:
            low = name.lower()
            if low in SYSTEM_DLLS or low.startswith(("api-ms-", "ext-ms-")):
                continue
            found = index.get(low)
            if found is None:
                missing.append((name, path))
            else:
                todo.append(found)
    return len(seen), missing


def main() -> int:
    say("STL2STEP Windows diagnostic")
    say("=" * 60)
    say("python:", sys.version.replace("\n", " "))
    say("executable:", sys.executable)
    say("cwd:", os.getcwd())
    say("root:", ROOT)
    say("PATH:", os.environ.get("PATH", ""))
    say("")

    for label, path in (
        ("OCP dir", OCP),
        ("OCP extension", OCP_PYD),
        ("cadquery_ocp.libs", os.path.join(SITE, "cadquery_ocp.libs")),
        ("vtk.libs", os.path.join(SITE, "vtk.libs")),
    ):
        state = "OK" if os.path.exists(path) else "MISSING"
        say(f"{label}: {state} ({path})")
    say("")

    if not os.path.exists(OCP_PYD):
        say("ERRORE: OCP.cp312-win_amd64.pyd non trovato.")
        return 1

    try:
        index = index_files()
        count, missing = walk(OCP_PYD, index)
        say(f"Moduli PE analizzati: {count}")
        if missing:
            say("")
            say("DIPENDENZE NON TROVATE:")
            for name, parent in sorted(set(missing)):
                say(f"  {name}")
                say(f"      richiesto da: {parent}")
        else:
            say("Tutte le dipendenze statiche risultano presenti.")
    except Exception:
        say("Analisi dipendenze non riuscita:")
        say(traceback.format_exc())

    say("")
    say("Prova di caricamento con ctypes:")
    for directory in (ROOT, OCP, os.path.join(SITE, "cadquery_ocp.libs"),
                      os.path.join(SITE, "vtk.libs")):
        if os.path.isdir(directory):
            try:
                os.add_dll_directory(directory)
                say(f"  add_dll_directory OK: {directory}")
            except Exception as exc:  # noqa: BLE001
                say(f"  add_dll_directory FALLITO: {directory}: {exc}")
    try:
        ctypes.WinDLL(OCP_PYD)
        say("  OCP.cp312-win_amd64.pyd caricata correttamente.")
    except Exception as exc:  # noqa: BLE001
        say(f"  OCP.cp312-win_amd64.pyd NON caricata: {exc!r}")
        say(f"  WinError: {getattr(exc, 'winerror', None)}")

    say("")
    say("Prova import OCP (traceback completo):")
    sys.path.insert(0, SITE)
    try:
        import OCP  # noqa: F401

        say("  import OCP OK, versione:", getattr(OCP, "__version__", "?"))
    except Exception:
        say(traceback.format_exc())

    say("")
    say("Contenuto OCP (prime 40 voci):")
    for name in sorted(os.listdir(OCP))[:40]:
        say("  ", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
