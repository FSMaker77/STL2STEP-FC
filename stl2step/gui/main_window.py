"""Main application window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.convert import ConversionParams
from ..core.mesh import Mesh
from ..version import APP_NAME
from .params_panel import ParamsPanel
from .preview import MeshPreview
from .worker import ConvertWorker


class _LoadWorker(QThread):
    loaded = Signal(object, str)
    failed = Signal(str, str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self) -> None:
        try:
            mesh = Mesh.from_stl(self.path)
            self.loaded.emit(mesh, self.path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(self.path, f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__} — Convertitore STL → STEP")
        self.resize(1280, 800)

        self._queue: list[tuple[str, str]] = []  # (input, output)
        self._worker: ConvertWorker | None = None
        self._loader: _LoadWorker | None = None
        self._preview_mesh: Mesh | None = None

        self._build_ui()
        self._build_menu()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Converti mesh STL in modelli STEP modificabili")
        subtitle.setObjectName("subtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch(1)
        self.add_btn = QPushButton("Aggiungi file…")
        self.add_btn.clicked.connect(self._add_files)
        self.add_dir_btn = QPushButton("Aggiungi cartella…")
        self.add_dir_btn.clicked.connect(self._add_dir)
        self.clear_btn = QPushButton("Svuota")
        self.clear_btn.clicked.connect(self._clear_queue)
        for b in (self.add_btn, self.add_dir_btn, self.clear_btn):
            header.addWidget(b)
        root.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)

        # left: file queue
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Coda di conversione"))
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self._on_select)
        ll.addWidget(self.file_list)

        self.output_btn = QPushButton("Cartella di output…")
        self.output_btn.clicked.connect(self._choose_output)
        ll.addWidget(self.output_btn)
        self.output_label = QLabel("Output: accanto al file sorgente")
        self.output_label.setObjectName("muted")
        self.output_label.setWordWrap(True)
        ll.addWidget(self.output_label)
        splitter.addWidget(left)

        # center: preview + stats
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        self.preview = MeshPreview()
        cl.addWidget(self.preview, stretch=1)

        stats = QHBoxLayout()
        self.stat_verts = self._stat_label(stats, "Vertici")
        self.stat_faces = self._stat_label(stats, "Facce")
        self.stat_water = self._stat_label(stats, "Chiuso")
        self.stat_vol = self._stat_label(stats, "Volume")
        cl.addLayout(stats)
        splitter.addWidget(center)

        # right: params + convert
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.params = ParamsPanel()
        rl.addWidget(self.params)

        self.convert_btn = QPushButton("Converti tutto")
        self.convert_btn.setObjectName("primary")
        self.convert_btn.setMinimumHeight(44)
        self.convert_btn.clicked.connect(self._convert_all)
        rl.addWidget(self.convert_btn)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([280, 600, 340])
        root.addWidget(splitter, stretch=1)

        # bottom: progress + log
        bottom = QVBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        bottom.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        bottom.addWidget(self.log)
        root.addLayout(bottom)

    def _stat_label(self, layout: QHBoxLayout, name: str) -> QLabel:
        col = QVBoxLayout()
        cap = QLabel(name)
        cap.setObjectName("stat")
        val = QLabel("—")
        val.setObjectName("statValue")
        col.addWidget(cap)
        col.addWidget(val)
        layout.addLayout(col)
        layout.addStretch(1)
        return val

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addAction("Aggiungi file…", self._add_files)
        file_menu.addAction("Aggiungi cartella…", self._add_dir)
        file_menu.addSeparator()
        file_menu.addAction("Esci", self.close)

        help_menu = bar.addMenu("&Aiuto")
        help_menu.addAction("Informazioni", self._about)

    # ---------------------------------------------------------------- actions
    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleziona file STL", "", "File STL (*.stl *.STL);;Tutti i file (*)"
        )
        for p in paths:
            self._enqueue(p)

    def _add_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Seleziona cartella con STL")
        if not d:
            return
        for p in sorted(Path(d).glob("*.stl")) + sorted(Path(d).glob("*.STL")):
            self._enqueue(str(p))

    def _enqueue(self, path: str) -> None:
        if any(p == path for p, _ in self._queue):
            return
        self._queue.append((path, ""))
        item = QListWidgetItem(Path(path).name)
        item.setToolTip(path)
        self.file_list.addItem(item)
        self.log.appendPlainText(f"Aggiunto: {path}")
        if self.file_list.count() == 1:
            self.file_list.setCurrentRow(0)

    def _clear_queue(self) -> None:
        self._queue.clear()
        self.file_list.clear()
        self.preview.set_mesh(None)
        self._reset_stats()

    def _choose_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Cartella di output")
        if d:
            self.output_label.setText(f"Output: {d}")
        else:
            self.output_label.setText("Output: accanto al file sorgente")

    def _output_dir(self) -> str | None:
        text = self.output_label.text()
        if text.startswith("Output: ") and text != "Output: accanto al file sorgente":
            return text[len("Output: "):]
        return None

    # ---------------------------------------------------------------- preview
    def _on_select(self, current: QListWidgetItem | None, _prev=None) -> None:
        if current is None:
            return
        idx = self.file_list.row(current)
        if idx < 0 or idx >= len(self._queue):
            return
        path = self._queue[idx][0]
        self._loader = _LoadWorker(path)
        self._loader.loaded.connect(self._mesh_loaded)
        self._loader.failed.connect(self._mesh_failed)
        self._loader.start()

    def _mesh_loaded(self, mesh: Mesh, _path: str) -> None:
        self._preview_mesh = mesh
        self.preview.set_mesh(mesh)
        s = mesh.summary()
        self.stat_verts.setText(f"{s['vertices']:,}")
        self.stat_faces.setText(f"{s['faces']:,}")
        self.stat_water.setText("Sì" if s["watertight"] else "No")
        self.stat_vol.setText(f"{s['volume']:.3f}")

    def _mesh_failed(self, path: str, err: str) -> None:
        self.preview.set_mesh(None)
        self._reset_stats()
        self.log.appendPlainText(f"Anteprima non disponibile per {path}: {err}")

    def _reset_stats(self) -> None:
        for w in (self.stat_verts, self.stat_faces, self.stat_water, self.stat_vol):
            w.setText("—")

    # ---------------------------------------------------------------- convert
    def _convert_all(self) -> None:
        if not self._queue:
            QMessageBox.information(self, "Nessun file", "Aggiungi almeno un file STL.")
            return

        params = self.params.build_params()
        out_dir = self._output_dir()

        for i, (inp, _) in enumerate(self._queue):
            out = self._output_path(inp, out_dir)
            self._queue[i] = (inp, out)

        self.add_btn.setEnabled(False)
        self.add_dir_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.convert_btn.setEnabled(False)
        self.progress.setValue(0)
        self.log.appendPlainText("— Inizio conversione —")
        self._start_next(params)

    def _output_path(self, inp: str, out_dir: str | None) -> str:
        src = Path(inp)
        if out_dir:
            return str(Path(out_dir) / f"{src.stem}.step")
        return str(src.with_suffix(".step"))

    def _start_next(self, params: ConversionParams) -> None:
        pending = [(i, p, o) for i, (p, o) in enumerate(self._queue) if not Path(o).exists()]
        if not pending:
            self._finish_all()
            return
        idx, inp, out = pending[0]
        self.log.appendPlainText(f"Conversione di {Path(inp).name} …")
        self.progress.setValue(0)
        self._worker = ConvertWorker(inp, out, params)
        self._worker.progress.connect(lambda s, f, m: self._on_progress(f, m))
        self._worker.done.connect(lambda res: self._on_done(idx, res))
        self._worker.failed.connect(lambda err: self._on_failed(idx, inp, err))
        self._worker.start()

    def _on_progress(self, frac: float, message: str) -> None:
        self.progress.setValue(int(frac * 100))
        if message:
            self.progress.setFormat(f"{message} — %p%")

    def _on_done(self, idx: int, result) -> None:
        self.progress.setValue(100)
        self.progress.setFormat("%p%")
        item = self.file_list.item(idx)
        item.setText(f"{Path(self._queue[idx][0]).name}  ✓ {Path(self._queue[idx][1]).name}")
        kind = "parametrico" if result.mode_used == "parametric" else "tassellato"
        extra = (
            f" — {result.n_planar} piani, {result.n_cylinders} cilindri, "
            f"{result.n_spheres} sfere"
            if result.mode_used == "parametric"
            else ""
        )
        self.log.appendPlainText(
            f"✓ {Path(result.output_path).name} ({kind}, volume {result.solid_volume:.3f}){extra}"
        )
        if result.preview_mesh is not None:
            self._preview_mesh = result.preview_mesh
            self.preview.set_mesh(result.preview_mesh)
            self.log.appendPlainText(f"Anteprima STEP: {Path(result.output_path).name}")
        self._start_next(self.params.build_params())

    def _on_failed(self, idx: int, inp: str, err: str) -> None:
        self.log.appendPlainText(f"✗ Errore su {Path(inp).name}: {err}")
        item = self.file_list.item(idx)
        item.setText(f"{Path(inp).name}  ✗ errore")
        self._start_next(self.params.build_params())

    def _finish_all(self) -> None:
        self.add_btn.setEnabled(True)
        self.add_dir_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.convert_btn.setEnabled(True)
        self.progress.setFormat("%p%")
        self.log.appendPlainText("— Conversione completata —")
        QMessageBox.information(self, "Completato", "Conversione terminata.")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "Informazioni su STL2STEP",
            f"<b>STL2STEP {__version__}</b><br><br>"
            "Converte mesh STL (stampa 3D) in modelli STEP modificabili,<br>"
            "con ricostruzione parametrica (piani e cilindri) e modalità tassellata.<br><br>"
            "Motore: OpenCASCADE (OCP) · GUI: PySide6<br>"
            "Software open source.",
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        if self._loader is not None and self._loader.isRunning():
            self._loader.wait(1000)
        super().closeEvent(event)
