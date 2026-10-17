"""Analytic primitive fitting (plane, sphere, cylinder, cone).

Each ``fit_*`` function takes point samples (and, where useful, their unit
normals) and returns a compact description of the best-fit primitive. These
descriptions are consumed by the BRep builder to reconstruct editable faces.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from scipy.optimize import least_squares


@dataclass
class Plane:
    point: np.ndarray  # (3,) a point on the plane
    normal: np.ndarray  # (3,) unit normal


@dataclass
class Sphere:
    center: np.ndarray  # (3,)
    radius: float


@dataclass
class Cylinder:
    axis_point: np.ndarray  # (3,) a point on the axis
    axis_dir: np.ndarray  # (3,) unit axis direction
    radius: float


@dataclass
class Cone:
    apex: np.ndarray  # (3,)
    axis_dir: np.ndarray  # (3,) unit direction from apex to base
    half_angle: float  # radians


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-12:
        return np.array([0.0, 0.0, 1.0])
    return v / n


def _axis_from(theta: float, phi: float) -> np.ndarray:
    return np.array(
        [math.sin(phi) * math.cos(theta), math.sin(phi) * math.sin(theta), math.cos(phi)]
    )


def fit_plane(points: np.ndarray) -> Plane:
    """Best-fit plane through a set of points (SVD / total least squares)."""
    points = np.asarray(points, dtype=np.float64)
    centroid = points.mean(axis=0)
    centered = points - centroid
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    normal = vh[-1]
    if normal[2] < 0:
        normal = -normal
    return Plane(point=centroid, normal=normal)


def plane_distances(points: np.ndarray, plane: Plane) -> np.ndarray:
    return np.abs((points - plane.point) @ plane.normal)


def fit_sphere(points: np.ndarray) -> Sphere:
    """Best-fit sphere via linear least squares on the sphere equation."""
    points = np.asarray(points, dtype=np.float64)
    x, y, z = points.T
    a = np.column_stack([x, y, z, np.ones(len(points))])
    b = x * x + y * y + z * z
    coeffs, *_ = np.linalg.lstsq(a, b, rcond=None)
    center = 0.5 * coeffs[:3]
    radius = float(np.sqrt(max(coeffs[3] + float(center @ center), 0.0)))
    return Sphere(center=center, radius=max(radius, 0.0))


def _estimate_axis_from_normals(normals: np.ndarray) -> np.ndarray:
    """Axis of a rotational surface = direction most orthogonal to the normals."""
    normals = np.asarray(normals, dtype=np.float64)
    if len(normals) < 2:
        return np.array([0.0, 0.0, 1.0])
    _, _, vh = np.linalg.svd(normals, full_matrices=False)
    return _unit(vh[-1])


def fit_cylinder(points: np.ndarray, normals: Optional[np.ndarray] = None) -> Cylinder:
    """Best-fit cylinder: robust nonlinear least squares on (axis, radius)."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) == 0:
        return Cylinder(np.zeros(3), np.array([0.0, 0.0, 1.0]), 0.0)

    centroid = points.mean(axis=0)
    if normals is not None and len(normals) >= 2:
        axis0 = _estimate_axis_from_normals(np.asarray(normals, dtype=np.float64))
    else:
        axis0 = np.array([0.0, 0.0, 1.0])

    to_axis = points - centroid
    radial0 = to_axis - (to_axis @ axis0)[:, None] * axis0
    r0 = float(np.median(np.linalg.norm(radial0, axis=1)))
    if r0 <= 0:
        r0 = 1.0

    theta0 = math.atan2(axis0[1], axis0[0])
    phi0 = math.acos(float(np.clip(axis0[2], -1.0, 1.0)))

    def residuals(p):
        d = _axis_from(p[0], p[1])
        axis_point = centroid - (centroid @ d) * d
        to_axis = points - axis_point
        radial = to_axis - (to_axis @ d)[:, None] * d
        return np.linalg.norm(radial, axis=1) - p[2]

    p0 = np.array([theta0, phi0, r0])
    try:
        result = least_squares(
            residuals, p0, method="trf", loss="soft_l1", f_scale=max(r0 * 0.1, 1e-6), max_nfev=100
        )
        theta, phi, radius = result.x
    except Exception:
        theta, phi, radius = theta0, phi0, r0

    d = _axis_from(theta, phi)
    axis_point = centroid - (centroid @ d) * d
    return Cylinder(axis_point=axis_point, axis_dir=d, radius=float(radius))


def _fit_line_ransac(along: np.ndarray, radial: np.ndarray, tol: float = 0.02):
    """Robust 2D line fit (radial = m*along + c), ignoring outlier points."""
    n = len(along)
    if n < 2:
        return 0.0, 0.0
    rng = np.random.default_rng(3)
    best = None
    for _ in range(min(300, n * 4)):
        i, j = rng.integers(0, n, size=2)
        if i == j:
            continue
        da = float(along[i] - along[j])
        if abs(da) < 1e-12:
            continue
        m = (radial[i] - radial[j]) / da
        if m < 0:
            continue
        c = radial[i] - m * along[i]
        resid = np.abs(radial - (m * along + c))
        score = int((resid <= tol).sum())
        if best is None or score > best[0]:
            best = (score, m, c)
    if best is None:
        return 0.0, float(np.median(radial))
    return best[1], best[2]


def fit_cone(
    points: np.ndarray, normals: Optional[np.ndarray] = None
) -> Cone:
    """Best-fit right circular cone.

    For a cone the surface normals are symmetrically distributed *around* the
    axis, so their average gives the axis direction directly. The apex and
    half-angle then come from a robust RANSAC line fit of ``(radial distance,
    axial distance)`` in a slice through the axis.
    """
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 3:
        return Cone(np.zeros(3), np.array([0.0, 0.0, 1.0]), 0.1)

    if normals is not None and len(normals) >= 2:
        mean_n = np.asarray(normals, dtype=np.float64).mean(axis=0)
        axis = _unit(mean_n)
    else:
        axis = np.array([0.0, 0.0, 1.0])

    centroid = points.mean(axis=0)
    to_c = points - centroid
    along = to_c @ axis
    radial = np.linalg.norm(to_c - along[:, None] * axis, axis=1)

    m, c = _fit_line_ransac(along, radial)
    if m <= 0:
        axis = -axis
        along = -along
        m, c = _fit_line_ransac(along, radial)
        if m <= 0:
            return Cone(centroid, axis, 0.1)

    half_angle = math.atan(m)
    apex = centroid + (-c / m) * axis
    return Cone(apex=apex, axis_dir=axis, half_angle=half_angle)
