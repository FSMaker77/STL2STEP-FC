"""Rebuild OCC BRep faces and solids from segmented meshes.

The builder turns analytic segments back into real CAD faces:

* planar regions  -> trimmed planar faces (holes supported)
* cylindrical     -> trimmed cylindrical faces (arc / generator boundary)
* other regions   -> triangulated faces (faithful fallback, always valid)

Faces are sewn into a shell and, when the mesh is closed, into a solid.
"""

from __future__ import annotations

import math
import tempfile
from collections import defaultdict
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from . import primitives as prim
from .mesh import Mesh
from .segmentation import Segment


# --------------------------------------------------------------------------- OCP imports
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Circ, gp_Pln  # noqa: E402
from OCP.BRepBuilderAPI import (  # noqa: E402
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeSolid,
    BRepBuilderAPI_Sewing,
)
from OCP.BRepCheck import BRepCheck_Analyzer  # noqa: E402
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape, TopoDS_Shell  # noqa: E402
from OCP.StlAPI import StlAPI_Reader  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL  # noqa: E402


# ---------------------------------------------------------------- boundary loops
def region_boundary_loops(mesh: Mesh, face_indices: Sequence[int]) -> List[List[int]]:
    """Return ordered boundary vertex-index loops of a triangle region."""
    directed: dict = defaultdict(int)
    for t in face_indices:
        a, b, c = (int(x) for x in mesh.faces[t])
        for u, v in ((a, b), (b, c), (c, a)):
            directed[(u, v)] += 1

    boundary = {(u, v) for (u, v), _ in directed.items() if directed.get((v, u), 0) == 0}
    nxt: dict = defaultdict(list)
    for u, v in boundary:
        nxt[u].append(v)

    loops: List[List[int]] = []
    used = set()
    for u, v in list(boundary):
        if (u, v) in used:
            continue
        loop = [u]
        cur = v
        used.add((u, v))
        while cur != u:
            loop.append(cur)
            candidates = [w for w in nxt[cur] if (cur, w) not in used]
            if not candidates:
                break
            nv = candidates[0]
            used.add((cur, nv))
            cur = nv
        if cur == u and len(loop) >= 3:
            loops.append(loop)
    return loops


def _project_to_plane(plane: prim.Plane, pts: np.ndarray) -> np.ndarray:
    return pts - ((pts - plane.point) @ plane.normal)[:, None] * plane.normal


def _polygon_area_2d(pts2d: np.ndarray) -> float:
    x, y = pts2d[:, 0], pts2d[:, 1]
    return float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) / 2.0)


def _basis_from_normal(normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    n = normal / np.linalg.norm(normal)
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return u, v


def _make_wire(points: List[Tuple[float, float, float]]) -> object:
    poly = BRepBuilderAPI_MakePolygon()
    for p in points:
        poly.Add(gp_Pnt(*p))
    poly.Close()
    return poly.Wire()


# ---------------------------------------------------------------- planar faces
def _try_circle(plane: prim.Plane, pts: np.ndarray, tol: float):
    """Fit a circle to coplanar points; return (center3d, radius) or None."""
    u, v = _basis_from_normal(plane.normal)
    d = pts - plane.point
    p2 = np.column_stack([d @ u, d @ v])
    x, y = p2[:, 0], p2[:, 1]
    a = np.column_stack([x, y, np.ones(len(p2))])
    b = -(x * x + y * y)
    try:
        dcoeff, ecoeff, fcoeff = np.linalg.lstsq(a, b, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    cx, cy = -dcoeff / 2.0, -ecoeff / 2.0
    r2 = cx * cx + cy * cy - fcoeff
    if not np.isfinite(r2) or r2 <= 0:
        return None
    radius = math.sqrt(r2)
    dist = np.abs(np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - radius)
    if float(np.median(dist)) > max(tol, 0.02 * radius):
        return None
    center = plane.point + cx * u + cy * v
    return center, radius


def _loop_wire(mesh: Mesh, plane: prim.Plane, loop: List[int], tol: float):
    """Build a boundary wire for one loop; analytic circle when circular."""
    pts = _project_to_plane(plane, mesh.vertices[np.asarray(loop)])
    circ = _try_circle(plane, pts, tol)
    if circ is not None:
        center, radius = circ
        edge = BRepBuilderAPI_MakeEdge(
            gp_Circ(gp_Ax2(gp_Pnt(*center), gp_Dir(*plane.normal)), radius)
        ).Edge()
        wire = BRepBuilderAPI_MakeWire()
        wire.Add(edge)
        return wire.Wire()
    return _make_wire([tuple(p) for p in pts])


def planar_face(mesh: Mesh, plane: prim.Plane, face_indices: Sequence[int]) -> Optional[TopoDS_Face]:
    loops = region_boundary_loops(mesh, face_indices)
    if not loops:
        return None

    u, v = _basis_from_normal(plane.normal)
    origin = plane.point

    def to_2d(loop: List[int]) -> np.ndarray:
        pts = _project_to_plane(plane, mesh.vertices[np.asarray(loop)])
        d = pts - origin
        return np.column_stack([d @ u, d @ v])

    loops_2d = [to_2d(loop) for loop in loops]
    areas = [_polygon_area_2d(l) for l in loops_2d]
    order = sorted(range(len(loops)), key=lambda i: -abs(areas[i]))
    outer = loops[order[0]]
    holes = [loops[i] for i in order[1:]]

    # use a circular boundary wherever the loop is (approximately) circular so
    # planar caps/seams match analytic cylinder faces during sewing
    try:
        mk = BRepBuilderAPI_MakeFace(
            gp_Pln(gp_Pnt(*plane.point), gp_Dir(*plane.normal)),
            _loop_wire(mesh, plane, outer, 0.02),
        )
        for hole in holes:
            mk.Add(_loop_wire(mesh, plane, hole, 0.02))
        face = mk.Face()
    except Exception:
        return None

    return face if _is_valid_face(face) else None


# ------------------------------------------------------------- cylinder faces
def _max_angular_gap(angles: np.ndarray) -> float:
    """Largest angular gap (radians) in a set of angles in [0, 2*pi)."""
    a = np.sort(np.mod(angles, 2 * math.pi))
    if len(a) < 2:
        return 2 * math.pi
    gaps = np.diff(a)
    return max(float(gaps.max()), 2 * math.pi - (a[-1] - a[0]))


def _full_cylinder_face(cyl: prim.Cylinder, h_min: float, h_max: float) -> Optional[TopoDS_Face]:
    from OCP.gp import gp_Ax3, gp_Cylinder

    surf = gp_Cylinder(gp_Ax3(gp_Pnt(*cyl.axis_point), gp_Dir(*cyl.axis_dir)), cyl.radius)
    mk = BRepBuilderAPI_MakeFace(surf, 0.0, 2 * math.pi, h_min, h_max)
    face = mk.Face()
    return face if _is_valid_face(face) else None


def cylinder_face(mesh: Mesh, cyl: prim.Cylinder, face_indices: Sequence[int]) -> Optional[TopoDS_Face]:
    """Reconstruct a trimmed cylindrical face from its region.

    Full 360-degree cylinders (holes, bosses, shafts) are rebuilt as a single
    analytic cylindrical face. Partial patches are attempted with arc/generator
    boundary curves and fall back to triangulation when they are not clean.
    """
    idx = np.asarray(list(face_indices))
    centroids = mesh.centroids[idx]
    u, v = _basis_from_normal(cyl.axis_dir)
    rel = centroids - cyl.axis_point
    angles = np.arctan2(rel @ v, rel @ u)

    # Recover the radius and axial extent from the *surface* vertices (centroids
    # sit inside the surface and are systematically wrong for tall triangles).
    verts = mesh.vertices[np.unique(mesh.faces[idx])]
    vrel = verts - cyl.axis_point
    vradial = vrel - (vrel @ cyl.axis_dir)[:, None] * cyl.axis_dir
    radius = float(np.median(np.linalg.norm(vradial, axis=1)))
    cyl = prim.Cylinder(axis_point=cyl.axis_point, axis_dir=cyl.axis_dir, radius=radius)
    vheights = vrel @ cyl.axis_dir
    h_min, h_max = float(vheights.min()), float(vheights.max())

    span = _max_angular_gap(angles)

    if span < 0.5:
        return _full_cylinder_face(cyl, h_min, h_max)

    return _partial_cylinder_face(mesh, cyl, face_indices)


def _partial_cylinder_face(
    mesh: Mesh, cyl: prim.Cylinder, face_indices: Sequence[int]
) -> Optional[TopoDS_Face]:
    loops = region_boundary_loops(mesh, face_indices)
    if not loops:
        return None

    u, v = _basis_from_normal(cyl.axis_dir)
    A = cyl.axis_point
    R = cyl.radius

    def surface_pt(p: np.ndarray) -> Tuple[np.ndarray, float, float]:
        to_a = p - A
        h = float(to_a @ cyl.axis_dir)
        radial = to_a - h * cyl.axis_dir
        ang = math.atan2(float(radial @ v), float(radial @ u))
        pt = A + R * math.cos(ang) * u + R * math.sin(ang) * v + h * cyl.axis_dir
        return pt, h, ang

    outer = max(loops, key=len)
    pts = mesh.vertices[np.asarray(outer)]
    projected = [surface_pt(p) for p in pts]

    tol = 1e-4 * max(R, 1.0)
    n = len(projected)
    edges: List[object] = []
    for i in range(n):
        p0, h0, a0 = projected[i]
        p1, h1, a1 = projected[(i + 1) % n]
        if abs(h1 - h0) <= tol:
            center = A + h0 * cyl.axis_dir
            circ = gp_Circ(gp_Ax2(gp_Pnt(*center), gp_Dir(*cyl.axis_dir)), R)
            da = a1 - a0
            da = (da + math.pi) % (2 * math.pi) - math.pi
            if abs(da) < 1e-6:
                return None
            try:
                edges.append(BRepBuilderAPI_MakeEdge(circ, a0, a1).Edge())
            except Exception:
                return None
        elif abs(a1 - a0) <= 1e-2 or abs(abs(a1 - a0) - 2 * math.pi) <= 1e-2:
            edges.append(BRepBuilderAPI_MakeEdge(gp_Pnt(*p0), gp_Pnt(*p1)).Edge())
        else:
            return None

    try:
        wire = BRepBuilderAPI_MakeWire()
        for e in edges:
            wire.Add(e)
        mk = BRepBuilderAPI_MakeFace(wire.Wire(), False)
        face = mk.Face()
    except Exception:
        return None

    return face if _is_valid_face(face) else None


# ------------------------------------------------------------- cone faces
def cone_face(mesh: Mesh, cone: prim.Cone, face_indices: Sequence[int]) -> Optional[TopoDS_Face]:
    """Reconstruct a full conical face (side of a cone/boss) via UV bounds."""
    from OCP.gp import gp_Ax3, gp_Cone

    idx = np.asarray(list(face_indices))
    centroids = mesh.centroids[idx]
    u, v = _basis_from_normal(cone.axis_dir)
    rel = centroids - cone.apex
    angles = np.arctan2(rel @ v, rel @ u)
    if _max_angular_gap(angles) >= 0.5:
        return None  # partial cone -> triangulation fallback

    verts = mesh.vertices[np.unique(mesh.faces[idx])]
    r = verts - cone.apex
    h = r @ cone.axis_dir
    # gp_Cone's V parameter is the slant distance along the generator
    cos_a = math.cos(cone.half_angle)
    v_min = float(h.min()) / cos_a
    v_max = float(h.max()) / cos_a

    try:
        surf = gp_Cone(gp_Ax3(gp_Pnt(*cone.apex), gp_Dir(*cone.axis_dir)), cone.half_angle, 0.0)
        mk = BRepBuilderAPI_MakeFace(surf, 0.0, 2 * math.pi, v_min, v_max)
        face = mk.Face()
    except Exception:
        return None
    return face if _is_valid_face(face) else None


# ------------------------------------------------------------ triangulation
def triangulate_faces(mesh: Mesh, face_indices: Sequence[int]) -> List[TopoDS_Face]:
    """Build triangular OCC faces from a set of mesh triangles (fast C++ path)."""
    face_indices = list(face_indices)
    if not face_indices:
        return []
    sub_faces = mesh.faces[np.asarray(face_indices, dtype=np.int64)]
    used = np.unique(sub_faces)
    remap = np.full(mesh.n_vertices, -1, dtype=np.int64)
    remap[used] = np.arange(len(used), dtype=np.int64)
    sub_vertices = mesh.vertices[used]
    sub_faces = remap[sub_faces]

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        from . import stl_io

        stl_io.write_stl(tmp.name, sub_vertices, sub_faces)

    shape = TopoDS_Shape()
    reader = StlAPI_Reader()
    reader.Read(shape, tmp.name)
    faces: List[TopoDS_Face] = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        faces.append(TopoDS.Face(ex.Current()))
        ex.Next()
    return faces


def _is_valid_face(face: TopoDS_Face) -> bool:
    try:
        if face.IsNull():
            return False
        analyzer = BRepCheck_Analyzer(face)
        return analyzer.IsValid()
    except Exception:
        return False


# ------------------------------------------------------------------- assembly
def build_solid(faces: Sequence[object], tol: float = 1e-5) -> Optional[TopoDS_Shape]:
    """Sew faces into a shell and, if closed, into a solid."""
    faces = [f for f in faces if f is not None]
    if not faces:
        return None
    sew = BRepBuilderAPI_Sewing(tol, True, True, True, False)
    for f in faces:
        sew.Add(f)
    sew.Perform()
    sewed = sew.SewedShape()

    shell: Optional[TopoDS_Shell] = None
    ex = TopExp_Explorer(sewed, TopAbs_SHELL)
    if ex.More():
        shell = TopoDS.Shell(ex.Current())
    if shell is None:
        return sewed

    try:
        mk = BRepBuilderAPI_MakeSolid(shell)
        if mk.IsDone():
            return mk.Solid()
    except Exception:
        pass
    return sewed


def collect_faces(shape: TopoDS_Shape) -> List[TopoDS_Face]:
    faces: List[TopoDS_Face] = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        faces.append(TopoDS.Face(ex.Current()))
        ex.Next()
    return faces


# ------------------------------------------------------------------- spheres
def sphere_solid(sph: prim.Sphere) -> Optional[TopoDS_Shape]:
    """Build an analytic solid sphere (used for full, closed spheres)."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere

    try:
        center = np.asarray(sph.center, dtype=np.float64) + 0.0  # normalise -0.0
        mk = BRepPrimAPI_MakeSphere(gp_Pnt(*center), float(sph.radius))
        solid = mk.Solid()
        if solid.IsNull():
            return None
        return solid
    except Exception:
        return None


def make_compound(shapes: Sequence[TopoDS_Shape]) -> TopoDS_Shape:
    """Combine several shapes (e.g. a sewn solid + solid spheres) into one."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        if shape is not None and not shape.IsNull():
            builder.Add(compound, shape)
    return compound
