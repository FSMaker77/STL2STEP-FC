"""Allow running with ``python -m stl2step``."""

import sys


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args:
        from .cli import main as cli_main

        return cli_main(args)
    from .gui.app import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
