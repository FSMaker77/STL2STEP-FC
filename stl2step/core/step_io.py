"""Read STEP files and tessellate OCC shapes back into triangle meshes.

Used by the GUI to preview the converted STEP result: the analytic BRep is
meshed with OpenCASCADE's incremental mesher and returned as plain
``(vertices, faces)`` arrays so it can reuse the same preview pipeline as STL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np

from OCP.STEPControl import STEPControl_Reader  # noqa: E402
from OCP.IFSelect import IFSelect_RetDone  # noqa: E402
from OCP.BRepMesh import BRepMesh_IncrementalMesh  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopAbs import TopAbs_FACE  # noqa: E402
from OCP.TopoDS import TopoDS, TopoDS_Shape  # noqa: E402
from OCP.BRep import BRep_Tool  # noqa: E402
from OCP.TopLoc import TopLoc_Location  # noqa: E402


def tessellate_shape(
    shape: TopoDS_Shape,
    linear_deflection: float = 0.05,
    angular_deflection: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """Mesh every face of ``shape`` into a shared triangle soup.

    Returns ``(vertices (N,3), faces (M,3))`` as float64 / int64 arrays.
    """
    BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection, True)

    verts: list = []
    faces: list = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face(ex.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None and tri.NbTriangles() > 0:
            nodes = []
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i)
                p.Transform(loc.Transformation())
                nodes.append((p.X(), p.Y(), p.Z()))
            base = len(verts)
            verts.extend(nodes)
            for i in range(1, tri.NbTriangles() + 1):
                n1, n2, n3 = tri.Triangle(i).Get()
                faces.append((base + n1 - 1, base + n2 - 1, base + n3 - 1))
        ex.Next()

    if not verts:
        raise ValueError("Nessun triangolo nella tassellazione STEP")

    return (
        np.asarray(verts, dtype=np.float64),
        np.asarray(faces, dtype=np.int64),
    )


def load_step(
    path: str,
    linear_deflection: float = 0.05,
    angular_deflection: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """Read a STEP file and return its tessellated ``(vertices, faces)``."""
    if not Path(path).exists():
        raise FileNotFoundError(path)

    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise ValueError("STEP non leggibile")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise ValueError("STEP senza geometria")

    return tessellate_shape(shape, linear_deflection, angular_deflection)
