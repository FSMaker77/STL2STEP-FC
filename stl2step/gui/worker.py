"""Background conversion worker (keeps the UI responsive)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.convert import ConversionParams, ConversionResult, convert_stl_to_step


class ConvertWorker(QThread):
    progress = Signal(str, float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, input_path: str, output_path: str, params: ConversionParams, parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.params = params
        self.with_preview = True
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:  # noqa: D401
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
