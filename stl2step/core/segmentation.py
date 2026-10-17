"""Mesh segmentation into analytic primitives (planes, cylinders, spheres).

Cylinders and spheres are detected first with global RANSAC (sampling distant
triangles gives a reliable axis / center, unlike a local greedy bootstrap).
Planes are then recovered on the remaining faces with a greedy region grower.
Any face left unclaimed is triangulated by the caller, so geometry is never
lost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np

from .mesh import Mesh
from . import primitives as prim

_MAX_REFIT_SAMPLES = 3000


@dataclass
class Segment:
    kind: str  # 'plane' | 'cylinder' | 'sphere' | 'cone'
    face_indices: np.ndarray
    plane: Optional[prim.Plane] = None
    cylinder: Optional[prim.Cylinder] = None
    sphere: Optional[prim.Sphere] = None
    cone: Optional[prim.Cone] = None
    residual: float = 0.0


@dataclass
class SegmentationParams:
    angular_tolerance_deg: float = 8.0
    distance_tolerance: float = 0.02
    min_region_faces: int = 6
    max_regions: int = 800
    detect_cylinders: bool = True
    detect_spheres: bool = True
    detect_cones: bool = False

    @property
    def angular_tolerance(self) -> float:
        return np.deg2rad(self.angular_tolerance_deg)


def _closest_approach(p1: np.ndarray, d1: np.ndarray, p2: np.ndarray, d2: np.ndarray) -> Optional[np.ndarray]:
    """Closest point between two lines (used to find a sphere centre)."""
    w0 = p1 - p2
    a = float(d1 @ d1)
    b = float(d1 @ d2)
    c = float(d2 @ d2)
    d = float(d1 @ w0)
    e = float(d2 @ w0)
    denom = a * c - b * b
    if abs(denom) < 1e-12:
        return None
    s = (b * e - c * d) / denom
    t = (a * e - b * d) / denom
    return 0.5 * ((p1 + s * d1) + (p2 + t * d2))


def _perp(d: np.ndarray) -> np.ndarray:
    ref = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(d, ref)
    return u / np.linalg.norm(u)


def _circle_from_3(a: np.ndarray, b: np.ndarray, c: np.ndarray):
    """Circle through three 2D points -> (center, radius) or None."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    denom = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(denom) < 1e-15:
        return None
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / denom
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / denom
    center = np.array([ux, uy])
    radius = float(np.linalg.norm(center - a))
    return center, radius


class Segmentation:
    def __init__(self, mesh: Mesh, params: SegmentationParams):
        self.mesh = mesh
        self.params = params
        self._adjacency = self._build_adjacency()
        self.segments: List[Segment] = []
        self.unassigned: Set[int] = set()

    # ------------------------------------------------------------------ topo
    def _build_adjacency(self) -> Dict[int, Set[int]]:
        faces = self.mesh.faces
        edge_map: Dict[tuple, List[int]] = {}
        for fi, (a, b, c) in enumerate(faces.tolist()):
            for e in ((a, b), (b, c), (c, a)):
                key = e if e[0] < e[1] else (e[1], e[0])
                edge_map.setdefault(key, []).append(fi)
        adjacency: Dict[int, Set[int]] = {i: set() for i in range(self.mesh.n_faces)}
        for owners in edge_map.values():
            for i in owners:
                for j in owners:
                    if i != j:
                        adjacency[i].add(j)
        return adjacency

    def _neighbors(self, fi: int) -> Set[int]:
        return self._adjacency.get(fi, set())

    def _largest_component(self, face_set: Set[int]) -> Set[int]:
        """Largest edge-connected component of a set of faces."""
        return max(self._all_components(face_set), key=len, default=set())

    def _all_components(self, face_set: Set[int]) -> List[Set[int]]:
        """Every edge-connected component of a set of faces."""
        unseen = set(face_set)
        components: List[Set[int]] = []
        while unseen:
            start = unseen.pop()
            stack = [start]
            comp = {start}
            while stack:
                fi = stack.pop()
                for nbr in self._neighbors(fi):
                    if nbr in unseen:
                        unseen.remove(nbr)
                        comp.add(nbr)
                        stack.append(nbr)
            components.append(comp)
        return components

    # ------------------------------------------------------------------ run
    def run(self) -> List[Segment]:
        self.segments = []
        self.unassigned = set()

        remaining: Set[int] = set(range(self.mesh.n_faces))

        if self.params.detect_cones:
            self._ransac_cones(remaining)
        if self.params.detect_spheres:
            self._ransac_spheres(remaining)
        if self.params.detect_cylinders:
            self._ransac_cylinders(remaining)
        self._grow_planar(remaining)

        self.unassigned = remaining
        return self.segments

    # ------------------------------------------------------- RANSAC cylinder
    def _ransac_cylinders(self, remaining: Set[int]) -> None:
        mesh = self.mesh
        tol = self.params.distance_tolerance
        sin_ang = float(np.sin(self.params.angular_tolerance))
        min_f = self.params.min_region_faces
        min_curved = max(min_f * 2, 12)
        rng = np.random.default_rng(7)

        for _ in range(200):
            pool = np.array(sorted(remaining))
            if len(pool) < max(3, min_f):
                break
            centroids = mesh.centroids[pool]
            normals = mesh.normals[pool]

            best_score = 0
            best_axis_point = None
            best_d = None
            best_r = 0.0
            iters = min(800, max(120, len(pool) // 2))
            for _ in range(iters):
                i, j, k = rng.integers(0, len(pool), size=3)
                if len({i, j, k}) < 3:
                    continue
                d = np.cross(normals[i], normals[j])
                dn = float(np.linalg.norm(d))
                if dn < 0.3:
                    continue
                d = d / dn
                u = _perp(d)
                v = np.cross(d, u)
                pts3 = centroids[[i, j, k]]
                p2 = np.column_stack([(pts3 - pts3[0]) @ u, (pts3 - pts3[0]) @ v])
                circ = _circle_from_3(p2[0], p2[1], p2[2])
                if circ is None:
                    continue
                center2d, r = circ
                if r <= 1e-9:
                    continue
                axis_point = pts3[0] + center2d[0] * u + center2d[1] * v
                rel = centroids - axis_point
                radial = rel - (rel @ d)[:, None] * d
                dist = np.abs(np.linalg.norm(radial, axis=1) - r)
                ncons = np.abs(normals @ d)
                score = int(((dist <= tol) & (ncons <= sin_ang)).sum())
                if score > best_score:
                    best_score = score
                    best_axis_point = axis_point
                    best_d = d
                    best_r = r

            if best_score < min_curved:
                break

            rel = centroids - best_axis_point
            radial = rel - (rel @ best_d)[:, None] * best_d
            inlier_mask = (np.abs(np.linalg.norm(radial, axis=1) - best_r) <= tol) & (
                np.abs(normals @ best_d) <= sin_ang
            )
            comp = self._largest_component(set(pool[inlier_mask].tolist()))
            if len(comp) < min_curved:
                break

            idx = np.asarray(sorted(comp))
            cyl = prim.fit_cylinder(mesh.centroids[idx], mesh.normals[idx])
            rel = mesh.centroids[idx] - cyl.axis_point
            radial = rel - (rel @ cyl.axis_dir)[:, None] * cyl.axis_dir
            resid = float(np.median(np.abs(np.linalg.norm(radial, axis=1) - cyl.radius)))
            if resid > tol * 2.0:
                break

            self.segments.append(
                Segment(kind="cylinder", face_indices=idx, cylinder=cyl, residual=resid)
            )
            remaining.difference_update(comp)

    # --------------------------------------------------------- RANSAC sphere
    def _ransac_spheres(self, remaining: Set[int]) -> None:
        mesh = self.mesh
        tol = self.params.distance_tolerance
        sin_ang = float(np.sin(self.params.angular_tolerance))
        min_f = self.params.min_region_faces
        min_curved = max(min_f * 2, 12)
        rng = np.random.default_rng(11)

        for _ in range(200):
            pool = np.array(sorted(remaining))
            if len(pool) < max(2, min_f):
                break
            centroids = mesh.centroids[pool]
            normals = mesh.normals[pool]

            best_score = 0
            best_center = None
            best_r = 0.0
            iters = min(600, max(80, len(pool)))
            for _ in range(iters):
                i, j = rng.integers(0, len(pool), size=2)
                if i == j:
                    continue
                if abs(float(normals[i] @ normals[j])) > 0.9:
                    continue
                center = _closest_approach(centroids[i], normals[i], centroids[j], normals[j])
                if center is None:
                    continue
                r = float(np.linalg.norm(centroids[i] - center))
                if r <= 1e-9:
                    continue
                dist = np.abs(np.linalg.norm(centroids - center, axis=1) - r)
                score = int((dist <= tol).sum())
                if score > best_score:
                    best_score = score
                    best_center = center
                    best_r = r

            if best_score < min_curved:
                break

            d = np.linalg.norm(centroids - best_center, axis=1)
            radial = (centroids - best_center) / np.maximum(d[:, None], 1e-12)
            inlier_mask = (np.abs(d - best_r) <= tol) & (
                np.abs((normals * radial).sum(axis=1)) > np.cos(self.params.angular_tolerance)
            )
            inlier_faces = set(pool[inlier_mask].tolist())
            comp = self._largest_component(inlier_faces)
            if len(comp) < min_curved:
                break

            idx = np.asarray(sorted(comp))
            sph = prim.fit_sphere(mesh.centroids[idx])
            d = np.linalg.norm(mesh.centroids[idx] - sph.center, axis=1)
            resid = float(np.median(np.abs(d - sph.radius)))
            if resid > tol * 2.0:
                break

            self.segments.append(
                Segment(kind="sphere", face_indices=idx, sphere=sph, residual=resid)
            )
            remaining.difference_update(comp)

    # ---------------------------------------------------------- RANSAC cone
    def _ransac_cones(self, remaining: Set[int]) -> None:
        """Detect conical surfaces (per connected component, best-effort)."""
        mesh = self.mesh
        tol = self.params.distance_tolerance
        min_curved = max(self.params.min_region_faces * 2, 12)

        for comp in self._all_components(remaining):
            if len(comp) < min_curved:
                continue
            idx = np.asarray(sorted(comp))
            verts = mesh.vertices[np.unique(mesh.faces[idx])]
            normals = mesh.normals[idx]
            cone = prim.fit_cone(verts, normals)
            if cone.half_angle < 0.05:
                continue
            r = verts - cone.apex
            along = r @ cone.axis_dir
            radial = np.linalg.norm(r - along[:, None] * cone.axis_dir, axis=1)
            expected = along * math.tan(cone.half_angle)
            resid = float(np.median(np.abs(radial - expected)))
            if resid > tol * 2.0:
                continue

            # claim only the conical wall; the planar base stays for the
            # planar pass (its normal is parallel to the cone axis)
            n_axis = np.abs(normals @ cone.axis_dir)
            side = idx[n_axis < 0.9]
            if len(side) < min_curved:
                continue
            self.segments.append(
                Segment(kind="cone", face_indices=side, cone=cone, residual=resid)
            )
            remaining.difference_update(side.tolist())

    # ---------------------------------------------------------------- planar
    def _grow_planar(self, remaining: Set[int]) -> None:
        params = self.params
        tol = params.distance_tolerance
        cos_ang = float(np.cos(params.angular_tolerance))
        mesh = self.mesh

        order = np.argsort(-mesh.areas)
        for seed in order.tolist():
            if len(self.segments) >= params.max_regions:
                break
            if seed not in remaining:
                continue
            remaining.discard(seed)

            region = {seed}
            frontier = [seed]
            plane = prim.fit_plane(mesh.vertices[mesh.faces[seed]])

            while frontier:
                new_frontier: List[int] = []
                for fi in frontier:
                    for nbr in self._neighbors(fi):
                        if nbr not in remaining:
                            continue
                        n = mesh.normals[nbr]
                        if abs(float(n @ plane.normal)) < cos_ang:
                            continue
                        vs = mesh.vertices[mesh.faces[nbr]]
                        if float(prim.plane_distances(vs, plane).max()) > tol:
                            continue
                        region.add(nbr)
                        remaining.discard(nbr)
                        new_frontier.append(nbr)
                frontier = new_frontier
                if frontier:
                    idx = np.asarray(sorted(region))
                    if len(idx) > _MAX_REFIT_SAMPLES:
                        sample = np.random.default_rng(0).choice(idx, _MAX_REFIT_SAMPLES, replace=False)
                        idx = np.sort(sample)
                    plane = prim.fit_plane(mesh.vertices[np.unique(mesh.faces[idx])])

            if len(region) >= params.min_region_faces:
                self.segments.append(
                    Segment(kind="plane", face_indices=np.asarray(sorted(region)), plane=plane)
                )
            else:
                remaining.update(region)
