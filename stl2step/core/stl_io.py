"""Fast, dependency-light STL reading and writing (binary + ASCII).

The whole mesh pipeline works on numpy arrays so that cleanup, welding and
segmentation can run in vectorised C before touching the OCP CAD kernel.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Tuple

import numpy as np


def _read_binary(path: str) -> Tuple[np.ndarray, np.ndarray]:
    data = Path(path).read_bytes()
    if len(data) < 84:
        raise ValueError("file too small to be a binary STL")
    n_triangles = struct.unpack("<I", data[80:84])[0]
    expected = 84 + n_triangles * 50
    if len(data) < expected:
        raise ValueError("truncated binary STL (declared %d triangles)" % n_triangles)

    raw = np.frombuffer(data[84:expected], dtype=np.uint8).reshape(-1, 50)
    normals = raw[:, :12].view("<f4").reshape(-1, 3)
    coords = raw[:, 12:48].view("<f4").reshape(-1, 9)
    vertices = coords.reshape(-1, 3).astype(np.float64)
    faces = np.arange(n_triangles * 3, dtype=np.int64).reshape(-1, 3)
    return vertices, faces, normals.astype(np.float64)


def _read_ascii(path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices = []
    faces = []
    normals = []
    current_normal = None
    current_face = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "facet":
                current_normal = tuple(float(x) for x in parts[2:5])
            elif parts[0] == "vertex":
                vertices.append(tuple(float(x) for x in parts[1:4]))
                current_face.append(len(vertices) - 1)
            elif parts[0] == "endfacet":
                if len(current_face) == 3:
                    faces.append(current_face)
                    normals.append(current_normal or (0.0, 0.0, 0.0))
                current_face = []
    if not vertices:
        raise ValueError("no facets found in ASCII STL")
    return (
        np.asarray(vertices, dtype=np.float64),
        np.asarray(faces, dtype=np.int64),
        np.asarray(normals, dtype=np.float64),
    )


def is_binary(path: str) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(512)
    if b"facet" in head or b"solid" in head.lower():
        return False
    return True


def load_stl(path: str):
    """Load an STL file, returning ``(vertices (N,3), faces (M,3), normals (M,3))``."""
    if is_binary(path):
        vertices, faces, normals = _read_binary(path)
    else:
        vertices, faces, normals = _read_ascii(path)
    if faces.shape[0] == 0:
        raise ValueError("STL contains no triangles")
    return vertices, faces, normals


def write_stl(path: str, vertices: np.ndarray, faces: np.ndarray) -> None:
    """Write a binary STL from vertex and face arrays."""
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    n = faces.shape[0]
    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    normals = np.cross(b - a, c - a)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals = normals / lengths

    tri = np.concatenate([a, b, c], axis=1).astype("<f4")  # (n, 9)
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80)
        fh.write(struct.pack("<I", n))
        for i in range(n):
            fh.write(normals[i].astype("<f4").tobytes())
            fh.write(tri[i].tobytes())
            fh.write(struct.pack("<H", 0))
