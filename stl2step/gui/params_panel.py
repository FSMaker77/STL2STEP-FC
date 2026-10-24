"""Parameter panel: conversion profile + tunable settings."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.params import ConversionParams
from ..profiles import Profile, load_all


class ParamsPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profiles = load_all()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        profile_box = QGroupBox("Profilo di conversione")
        pf = QVBoxLayout(profile_box)
        self.profile_combo = QComboBox()
        for p in self._profiles:
            self.profile_combo.addItem(f"{p.name} — {p.description}", p.id)
        self.profile_combo.currentIndexChanged.connect(self._apply_profile)
        self.profile_desc = QLabel()
        self.profile_desc.setObjectName("muted")
        self.profile_desc.setWordWrap(True)
        pf.addWidget(self.profile_combo)
        pf.addWidget(self.profile_desc)
        layout.addWidget(profile_box)

        mode_box = QGroupBox("Modalità")
        mf = QFormLayout(mode_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Automatica (consigliata)", "auto")
        self.mode_combo.addItem("Parametrica (BRep modificabile)", "parametric")
        self.mode_combo.addItem("Tassellata (fedele, non parametrica)", "tessellated")
        self.mode_combo.currentIndexChanged.connect(self._notify)
        mf.addRow("Conversione", self.mode_combo)
        layout.addWidget(mode_box)

        tol_box = QGroupBox("Tolleranze")
        tf = QFormLayout(tol_box)
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(0.1, 60.0)
        self.angle_spin.setSuffix(" °")
        self.angle_spin.setDecimals(1)
        self.angle_spin.valueChanged.connect(self._notify)
        tf.addRow("Angolo max faccia", self.angle_spin)

        self.dist_spin = QDoubleSpinBox()
        self.dist_spin.setRange(0.0001, 100.0)
        self.dist_spin.setDecimals(4)
        self.dist_spin.setSingleStep(0.001)
        self.dist_spin.valueChanged.connect(self._notify)
        tf.addRow("Distanza (tolleranza)", self.dist_spin)

        self.min_faces_spin = QSpinBox()
        self.min_faces_spin.setRange(2, 10000)
        self.min_faces_spin.valueChanged.connect(self._notify)
        tf.addRow("Facce min per regione", self.min_faces_spin)
        layout.addWidget(tol_box)

        prim_box = QGroupBox("Primitive da rilevare")
        pf2 = QVBoxLayout(prim_box)
        self.cyl_check = QCheckBox("Cilindri")
        self.sph_check = QCheckBox("Sfere")
        self.cone_check = QCheckBox("Coni (sperimentale)")
        self.solid_check = QCheckBox("Genera solido se chiuso")
        self.solid_check.setChecked(True)
        for w in (self.cyl_check, self.sph_check, self.cone_check, self.solid_check):
            w.toggled.connect(self._notify)
            pf2.addWidget(w)
        layout.addWidget(prim_box)

        layout.addStretch(1)
        self._apply_profile(0)

    def _notify(self, *_args) -> None:
        self.changed.emit()

    def _apply_profile(self, index: int) -> None:
        profile: Profile = self._profiles[index]
        self.profile_desc.setText(profile.description)
        self.mode_combo.setCurrentIndex(
            {"auto": 0, "parametric": 1, "tessellated": 2}[profile.mode]
        )
        self.angle_spin.setValue(profile.angular_tolerance_deg)
        self.dist_spin.setValue(profile.distance_tolerance)
        self.min_faces_spin.setValue(profile.min_region_faces)
        self.cyl_check.setChecked(profile.detect_cylinders)
        self.sph_check.setChecked(profile.detect_spheres)
        self.cone_check.setChecked(profile.detect_cones)
        self.solid_check.setChecked(profile.make_solid)
        self.changed.emit()

    def current_profile_id(self) -> str:
        return self._profiles[self.profile_combo.currentIndex()].id

    def build_params(self) -> ConversionParams:
        return ConversionParams(
            mode=self.mode_combo.currentData(),
            angular_tolerance_deg=self.angle_spin.value(),
            distance_tolerance=self.dist_spin.value(),
            min_region_faces=self.min_faces_spin.value(),
            detect_cylinders=self.cyl_check.isChecked(),
            detect_spheres=self.sph_check.isChecked(),
            detect_cones=self.cone_check.isChecked(),
            make_solid=self.solid_check.isChecked(),
        )
