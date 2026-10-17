"""High-level conversion orchestration: STL in, editable STEP out."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from . import brep, stl_io
from .mesh import Mesh
from .segmentation import Segmentation, SegmentationParams

from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs  # noqa: E402
from OCP.TopoDS import TopoDS_Shape  # noqa: E402
from OCP.StlAPI import StlAPI_Reader  # noqa: E402
from OCP.IFSelect import IFSelect_RetDone  # noqa: E402


ProgressCallback = Callable[[str, float, str], None]


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

    def segmentation_params(self) -> SegmentationParams:
        return SegmentationParams(
            angular_tolerance_deg=self.angular_tolerance_deg,
            distance_tolerance=self.distance_tolerance,
            min_region_faces=self.min_region_faces,
            detect_cylinders=self.detect_cylinders,
            detect_spheres=self.detect_spheres,
            detect_cones=self.detect_cones,
        )


@dataclass
class ConversionResult:
    output_path: str
    mode_used: str
    n_vertices: int
    n_faces_in: int
    n_segments: int = 0
    n_planar: int = 0
    n_cylinders: int = 0
    n_spheres: int = 0
    n_cones: int = 0
    coverage: float = 0.0  # fraction of triangles assigned to a primitive
    is_solid: bool = False
    solid_volume: float = 0.0
    message: str = ""


def _noop_progress(stage: str, frac: float, message: str) -> None:
    pass


def _write_step(shape: TopoDS_Shape, path: str) -> bool:
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(path)
    return status == IFSelect_RetDone


def _shape_from_clean_mesh(mesh: Mesh, make_solid: bool, tol: float) -> Optional[TopoDS_Shape]:
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        stl_io.write_stl(tmp.name, mesh.vertices, mesh.faces)
    shape = TopoDS_Shape()
    if not StlAPI_Reader().Read(shape, tmp.name):
        return None
    if make_solid:
        faces = brep.collect_faces(shape)
        return brep.build_solid(faces, tol)
    return shape


def convert_stl_to_step(
    input_path: str,
    output_path: str,
    params: ConversionParams,
    progress: Optional[ProgressCallback] = None,
) -> ConversionResult:
    progress = progress or _noop_progress

    progress("load", 0.0, "Caricamento STL")
    mesh = Mesh.from_stl(input_path, weld=True, clean=True)
    n_vertices = mesh.n_vertices
    n_faces_in = mesh.n_faces

    mode = params.mode
    if mode == "auto":
        # organic / sculptural meshes convert best as tessellated STEP
        mode = "parametric" if n_faces_in <= 250_000 else "tessellated"

    result = ConversionResult(
        output_path=output_path,
        mode_used=mode,
        n_vertices=n_vertices,
        n_faces_in=n_faces_in,
    )

    if mode == "tessellated":
        progress("tessellate", 0.3, "Generazione STEP tassellato")
        shape = _shape_from_clean_mesh(mesh, params.make_solid, params.sewing_tolerance)
        if shape is None:
            raise RuntimeError("Impossibile costruire la geometria dal mesh")
        progress("write", 0.8, "Scrittura file STEP")
        if not _write_step(shape, output_path):
            raise RuntimeError("Scrittura STEP fallita")
        _record_shape_stats(shape, result)
        progress("done", 1.0, "Completato")
        result.message = "STEP tassellato (mesh come facce triangolari)"
        return result

    # ------------------------------------------------------------- parametric
    progress("segment", 0.25, "Segmentazione del mesh")
    seg = Segmentation(mesh, params.segmentation_params())
    segments = seg.run()

    progress("reconstruct", 0.55, "Ricostruzione facce CAD")
    faces = []
    solids = []
    covered = 0
    claimed: set = set()
    fallback: list = []
    for segment in segments:
        claimed.update(segment.face_indices.tolist())
        covered += len(segment.face_indices)
        face = None
        solid = None
        if segment.kind == "plane":
            face = brep.planar_face(mesh, segment.plane, segment.face_indices)
            result.n_planar += 1
        elif segment.kind == "cylinder":
            face = brep.cylinder_face(mesh, segment.cylinder, segment.face_indices)
            result.n_cylinders += 1
        elif segment.kind == "sphere":
            result.n_spheres += 1
            # a full (closed) sphere becomes an analytic solid; a partial
            # sphere (cap/hemisphere) falls back to triangulation
            if not brep.region_boundary_loops(mesh, segment.face_indices):
                solid = brep.sphere_solid(segment.sphere)
        elif segment.kind == "cone":
            result.n_cones += 1
            face = brep.cone_face(mesh, segment.cone, segment.face_indices)

        if solid is not None:
            solids.append(solid)
        elif face is not None:
            faces.append(face)
        else:
            # analytic reconstruction failed -> keep the mesh triangles for
            # these faces so no geometry is ever lost
            fallback.extend(segment.face_indices.tolist())

    leftover = [i for i in range(mesh.n_faces) if i not in claimed]
    fallback.extend(leftover)
    if fallback:
        progress("reconstruct", 0.7, "Triangolazione aree residue")
        faces.extend(brep.triangulate_faces(mesh, fallback))

    result.n_segments = len(segments)
    result.coverage = covered / max(n_faces_in, 1)

    progress("assemble", 0.85, "Assemblaggio solido")
    sew_tol = max(params.sewing_tolerance, params.distance_tolerance * 0.1)
    sewed = brep.build_solid(faces, sew_tol) if faces else None
    if solids and sewed is not None:
        shape = brep.make_compound([sewed, *solids])
    elif solids:
        shape = solids[0] if len(solids) == 1 else brep.make_compound(solids)
    elif sewed is not None:
        shape = sewed
    else:
        raise RuntimeError("Nessuna geometria ricostruita")

    _record_shape_stats(shape, result)

    # Safety net: if the parametric reconstruction diverged from the input mesh
    # (closed meshes have a reliable volume), fall back to a faithful tessellated
    # STEP so the result is always geometrically correct.
    if result.is_solid and mesh.is_watertight():
        mesh_vol = abs(mesh.volume())
        if mesh_vol > 0 and abs(result.solid_volume - mesh_vol) / mesh_vol > 0.05:
            progress("fallback", 0.9, "Ricostruzione parametrica non fedele — fallback tassellato")
            shape = _shape_from_clean_mesh(mesh, params.make_solid, params.sewing_tolerance)
            if shape is None:
                raise RuntimeError("Impossibile costruire la geometria dal mesh")
            result.mode_used = "tessellated"
            result.n_planar = result.n_cylinders = result.n_spheres = result.n_cones = 0
            result.n_segments = 0
            result.coverage = 0.0
            _record_shape_stats(shape, result)
            result.message = "STEP tassellato (fallback automatico)"

    progress("write", 0.92, "Scrittura file STEP")
    if not _write_step(shape, output_path):
        raise RuntimeError("Scrittura STEP fallita")

    progress("done", 1.0, "Completato")
    result.message = result.message or _describe_result(result)
    return result


def _describe_result(result: ConversionResult) -> str:
    parts = [f"{result.n_planar} piani"]
    if result.n_cylinders:
        parts.append(f"{result.n_cylinders} cilindri")
    if result.n_spheres:
        parts.append(f"{result.n_spheres} sfere")
    if result.n_cones:
        parts.append(f"{result.n_cones} coni")
    return "STEP parametrico (" + ", ".join(parts) + ")"


def _record_shape_stats(shape: TopoDS_Shape, result: ConversionResult) -> None:
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    result.is_solid = ex.More()
    if result.is_solid:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        result.solid_volume = abs(props.Mass())
