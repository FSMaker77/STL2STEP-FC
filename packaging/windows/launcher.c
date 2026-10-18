/*
 * Tiny Windows launcher for the bundled Python runtime.
 *
 * STL2STEP.exe       -> pythonw.exe -m stl2step        (GUI, no console)
 * stl2step-cli.exe   -> python.exe  -m stl2step.cli    (console, forwards args)
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

#ifndef GUI
#define GUI 0
#endif

static void fail(const wchar_t *msg)
{
#if GUI
    MessageBoxW(NULL, msg, L"STL2STEP FC", MB_ICONERROR | MB_OK);
#else
    fwprintf(stderr, L"%ls\n", msg);
#endif
}

#if GUI
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR pCmdLine, int nCmdShow)
{
    (void)hInst;
    (void)hPrev;
    (void)pCmdLine;
    (void)nCmdShow;
#else
int wmain(int argc, wchar_t **argv)
{
#endif
    wchar_t exe[MAX_PATH];
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) {
        fail(L"Impossibile determinare il percorso dell'eseguibile.");
        return 1;
    }

    wchar_t *slash = wcsrchr(exe, L'\\');
    if (slash == NULL) {
        fail(L"Percorso dell'eseguibile non valido.");
        return 1;
    }
    *slash = L'\0';

    wchar_t python[MAX_PATH];
    if (swprintf(python, MAX_PATH, L"%ls\\%ls", exe,
                 GUI ? L"pythonw.exe" : L"python.exe") < 0) {
        fail(L"Percorso troppo lungo.");
        return 1;
    }

    wchar_t cmd[32768];
#if GUI
    if (swprintf(cmd, 32768, L"\"%ls\" \"%ls\\stl2step_gui.pyw\"", python, exe) < 0) {
        fail(L"Riga di comando troppo lunga.");
        return 1;
    }
#else
    if (swprintf(cmd, 32768, L"\"%ls\" -m stl2step.cli", python) < 0) {
        fail(L"Riga di comando troppo lunga.");
        return 1;
    }
    for (int i = 1; i < argc; i++) {
        if (wcslen(cmd) + wcslen(argv[i]) + 4 >= 32768) {
            fail(L"Riga di comando troppo lunga.");
            return 1;
        }
        wcscat(cmd, L" \"");
        wcscat(cmd, argv[i]);
        wcscat(cmd, L"\"");
    }
#endif

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessW(python, cmd, NULL, NULL, TRUE, 0, NULL, exe, &si, &pi)) {
        wchar_t msg[1024];
        swprintf(msg, 1024, L"Impossibile avviare Python:\n%ls\n\nErrore %lu.",
                 python, GetLastError());
        fail(msg);
        return 1;
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}
