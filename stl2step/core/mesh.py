"""Triangle-mesh representation plus cleanup and repair utilities.

The :class:`Mesh` type holds vertices and indexed faces as contiguous numpy
arrays. Cleaning (welding, degenerate removal, re-indexing) is fully vectorised
so it stays fast even on meshes with hundreds of thousands of triangles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from . import stl_io


@dataclass
class Mesh:
    vertices: np.ndarray
    faces: np.ndarray
    normals: Optional[np.ndarray] = None
    areas: Optional[np.ndarray] = None
    centroids: Optional[np.ndarray] = None
    name: str = ""

    def __post_init__(self) -> None:
        self.vertices = np.ascontiguousarray(self.vertices, dtype=np.float64)
        self.faces = np.ascontiguousarray(self.faces, dtype=np.int64)
        self.recompute_geometry()

    @property
    def n_vertices(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def n_faces(self) -> int:
        return int(self.faces.shape[0])

    @property
    def bbox(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def recompute_geometry(self) -> None:
        a = self.vertices[self.faces[:, 0]]
        b = self.vertices[self.faces[:, 1]]
        c = self.vertices[self.faces[:, 2]]
        cross = np.cross(b - a, c - a)
        self.normals = cross / np.maximum(
            np.linalg.norm(cross, axis=1, keepdims=True), 1e-30
        )
        self.areas = 0.5 * np.linalg.norm(cross, axis=1)
        self.centroids = (a + b + c) / 3.0

    # ------------------------------------------------------------------ load
    @classmethod
    def from_stl(cls, path: str, weld: bool = True, clean: bool = True) -> "Mesh":
        vertices, faces, _ = stl_io.load_stl(path)
        mesh = cls(vertices=vertices, faces=faces)
        if weld:
            mesh = mesh.weld()
        if clean:
            mesh = mesh.remove_degenerate().remove_unreferenced()
        return mesh

    @classmethod
    def from_step(
        cls,
        path: str,
        linear_deflection: float = 0.05,
        angular_deflection: float = 0.5,
    ) -> "Mesh":
        from . import step_io

        vertices, faces = step_io.load_step(path, linear_deflection, angular_deflection)
        return cls(vertices=vertices, faces=faces, name=Path(path).name)

    def to_stl(self, path: str) -> None:
        stl_io.write_stl(path, self.vertices, self.faces)

    # --------------------------------------------------------------- cleanup
    def weld(self, decimals: int = 6) -> "Mesh":
        """Merge vertices that share the same (rounded) coordinate."""
        rounded = np.round(self.vertices, decimals=decimals)
        _, inverse = np.unique(rounded, axis=0, return_inverse=True)
        unique_idx, first = np.unique(inverse, return_index=True)
        new_vertices = self.vertices[first]
        order = np.argsort(unique_idx)
        remap = order[np.argsort(unique_idx)]  # map old-unique -> compact
        new_faces = remap[inverse[self.faces]].astype(np.int64)
        mesh = Mesh(new_vertices, new_faces, name=self.name)
        return mesh

    def remove_degenerate(self, eps_area: float = 1e-14) -> "Mesh":
        """Drop faces with zero area or repeated vertices."""
        keep = self.areas > eps_area
        return Mesh(self.vertices, self.faces[keep], name=self.name)

    def remove_unreferenced(self) -> "Mesh":
        used = np.unique(self.faces)
        remap = np.full(self.n_vertices, -1, dtype=np.int64)
        remap[used] = np.arange(len(used), dtype=np.int64)
        return Mesh(
            self.vertices[used],
            remap[self.faces],
            name=self.name,
        )

    def clean(self, decimals: int = 6, eps_area: float = 1e-14) -> "Mesh":
        return (
            self.weld(decimals).remove_degenerate(eps_area).remove_unreferenced()
        )

    # ------------------------------------------------------------- topology
    def boundary_edge_count(self) -> int:
        """Number of edges used by a single face (0 == watertight, ideally)."""
        f = self.faces
        e = np.vstack(
            [f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]
        )  # directed edges
        sorted_edges = np.sort(e, axis=1)
        _, counts = np.unique(sorted_edges, axis=0, return_counts=True)
        return int(np.count_nonzero(counts == 1))

    def is_watertight(self) -> bool:
        return self.boundary_edge_count() == 0

    def area(self) -> float:
        return float(self.areas.sum())

    def volume(self) -> float:
        """Signed volume via the divergence theorem (valid for closed meshes)."""
        v = self.vertices
        a = v[self.faces[:, 0]]
        b = v[self.faces[:, 1]]
        c = v[self.faces[:, 2]]
        return float(np.einsum("ij,ij->", a, np.cross(b, c)) / 6.0)

    # ---------------------------------------------------------------- stats
    def summary(self) -> dict:
        return {
            "vertices": self.n_vertices,
            "faces": self.n_faces,
            "area": self.area(),
            "volume": abs(self.volume()),
            "watertight": self.is_watertight(),
            "boundary_edges": self.boundary_edge_count(),
        }
