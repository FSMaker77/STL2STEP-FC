"""Windows GUI entry point with visible startup errors.

pythonw.exe has no console, so an import failure would otherwise be silent.
"""

import os
import sys
import traceback


def _show_error(text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0, text, "STL2STEP FC - errore", 0x10
        )
    except Exception:
        pass


def main() -> int:
    from stl2step.gui.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        details = traceback.format_exc()
        try:
            log_path = os.path.join(os.path.dirname(sys.executable), "stl2step-error.log")
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write(details)
        except Exception:
            pass
        _show_error(details)
        raise
