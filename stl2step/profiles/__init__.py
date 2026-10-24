"""Conversion profiles (ready-made parameter templates) and their loader."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..core.params import ConversionParams

_PROFILE_FIELDS = (
    "mode",
    "angular_tolerance_deg",
    "distance_tolerance",
    "min_region_faces",
    "detect_cylinders",
    "detect_spheres",
    "detect_cones",
    "make_solid",
    "sewing_tolerance",
    "weld_decimals",
)


@dataclass
class Profile:
    id: str
    name: str
    description: str = ""
    mode: str = "auto"
    angular_tolerance_deg: float = 6.0
    distance_tolerance: float = 0.02
    min_region_faces: int = 6
    detect_cylinders: bool = True
    detect_spheres: bool = True
    detect_cones: bool = False
    make_solid: bool = True
    sewing_tolerance: float = 1e-5
    weld_decimals: int = 6

    def to_params(self) -> ConversionParams:
        return ConversionParams(**{k: getattr(self, k) for k in _PROFILE_FIELDS})

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        known = {f: data[f] for f in _PROFILE_FIELDS if f in data}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            **known,
        )

    def to_dict(self) -> dict:
        return asdict(self)


def data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "profiles"


def load_all() -> List[Profile]:
    profiles: List[Profile] = []
    directory = data_dir()
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            try:
                profiles.append(Profile.from_dict(json.loads(path.read_text())))
            except (ValueError, json.JSONDecodeError):
                continue
    if not profiles:
        profiles = builtin_defaults()
    return profiles


def load_by_id(profile_id: str) -> Optional[Profile]:
    for p in load_all():
        if p.id == profile_id:
            return p
    return None


def builtin_defaults() -> List[Profile]:
    return [
        Profile(
            id="mechanical",
            name="Meccanico",
            description="Pezzi con facce piane e cilindriche. Ricostruzione parametrica.",
            mode="auto",
            angular_tolerance_deg=6.0,
            distance_tolerance=0.02,
            min_region_faces=6,
            detect_cylinders=True,
            detect_spheres=True,
            detect_cones=False,
        ),
        Profile(
            id="organic",
            name="Organico",
            description="Sculture e forme libere. STEP tassellato fedele.",
            mode="tessellated",
        ),
        Profile(
            id="high_precision",
            name="Alta precisione",
            description="Tolleranze strette per parti da riutilizzare in CAD.",
            mode="parametric",
            angular_tolerance_deg=3.0,
            distance_tolerance=0.005,
            min_region_faces=4,
            sewing_tolerance=1e-6,
        ),
        Profile(
            id="fast",
            name="Veloce",
            description="Conversione rapida con tolleranze ampie.",
            mode="auto",
            angular_tolerance_deg=15.0,
            distance_tolerance=0.1,
            min_region_faces=20,
        ),
    ]
