"""Allow running with ``python -m stl2step``."""

from .gui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
