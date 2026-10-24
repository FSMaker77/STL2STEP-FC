"""Background conversion worker (keeps the UI responsive)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

if TYPE_CHECKING:
    from ..core.params import ConversionParams


class ConvertWorker(QThread):
    progress = Signal(str, float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, input_path: str, output_path: str, params: "ConversionParams", parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.params = params
        self.with_preview = True
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D401
        # Imported here so that starting the GUI does not load OCP/SciPy.
        from ..core.convert import convert_stl_to_step

        try:
            result = convert_stl_to_step(
                self.input_path,
                self.output_path,
                self.params,
                progress=lambda s, f, m: self.progress.emit(s, f, m),
                with_preview=self.with_preview,
            )
            if self._cancelled:
                return
            self.done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
