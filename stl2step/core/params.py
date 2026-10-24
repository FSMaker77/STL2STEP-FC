"""Conversion parameters shared by the GUI, the CLI and the CAD engine.

This module deliberately has no heavy imports (no OCP, no SciPy) so that the
GUI can show its window without loading the whole CAD stack.  The real engine
is imported lazily the first time a conversion is started.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .segmentation import SegmentationParams


@dataclass
class ConversionParams:
    mode: str = "auto"  # 'auto' | 'parametric' | 'tessellated'
    angular_tolerance_deg: float = 6.0
    distance_tolerance: float = 0.02
    min_region_faces: int = 6
    detect_cylinders: bool = True
    detect_spheres: bool = True
    detect_cones: bool = False
    make_solid: bool = True
    sewing_tolerance: float = 1e-5
    weld_decimals: int = 6

    def segmentation_params(self) -> "SegmentationParams":
        # Imported here (and not at module level) because segmentation pulls
        # in SciPy, which would defeat the lazy startup.
        from .segmentation import SegmentationParams

        return SegmentationParams(
            angular_tolerance_deg=self.angular_tolerance_deg,
            distance_tolerance=self.distance_tolerance,
            min_region_faces=self.min_region_faces,
            detect_cylinders=self.detect_cylinders,
            detect_spheres=self.detect_spheres,
            detect_cones=self.detect_cones,
        )
