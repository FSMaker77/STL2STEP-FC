"""Generate sample STL files used for tests and manual demos."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stl2step.core import stl_io  # noqa: E402


def box(size=(1.0, 1.0, 1.0)):
    x, y, z = size
    c = np.array(
        [
            [0, 0, 0], [x, 0, 0], [x, y, 0], [0, y, 0],
            [0, 0, z], [x, 0, z], [x, y, z], [0, y, z],
        ],
        dtype=np.float64,
    )
    quads = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    faces = []
    for q in quads:
        faces.append([q[0], q[1], q[2]])
        faces.append([q[0], q[2], q[3]])
    return c, np.asarray(faces, dtype=np.int64)


def cylinder(radius=0.5, height=1.0, segments=64):
    verts = []
    faces = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts.append([radius * math.cos(a), radius * math.sin(a), 0.0])
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts.append([radius * math.cos(a), radius * math.sin(a), height])
    bottom_center = 2 * segments
    top_center = 2 * segments + 1
    verts.append([0.0, 0.0, 0.0])
    verts.append([0.0, 0.0, height])

    for i in range(segments):
        j = (i + 1) % segments
        b0, b1 = i, j
        t0, t1 = segments + i, segments + j
        faces.append([b0, t1, t0])
        faces.append([b0, b1, t1])
        faces.append([bottom_center, b1, b0])
        faces.append([top_center, t0, t1])
    return np.asarray(verts), np.asarray(faces, dtype=np.int64)


def sphere(radius=0.5, segments=48):
    verts = [[0, 0, radius]]
    faces = []
    for ring in range(1, segments):
        phi = math.pi * ring / segments
        z = radius * math.cos(phi)
        r = radius * math.sin(phi)
        ring_start = len(verts)
        for i in range(segments):
            th = 2 * math.pi * i / segments
            verts.append([r * math.cos(th), r * math.sin(th), z])
        ring_end = len(verts)
        if ring == 1:
            for i in range(segments):
                nxt = (i + 1) % segments
                faces.append([0, ring_start + nxt, ring_start + i])
        else:
            prev_start = ring_start - segments
            for i in range(segments):
                nxt = (i + 1) % segments
                a = prev_start + i
                b = prev_start + nxt
                c = ring_start + i
                d = ring_start + nxt
                faces.append([a, b, c])
                faces.append([b, d, c])
    bottom = len(verts)
    verts.append([0, 0, -radius])
    last_start = len(verts) - segments - 1
    for i in range(segments):
        nxt = (i + 1) % segments
        faces.append([bottom, last_start + i, last_start + nxt])
    return np.asarray(verts), np.asarray(faces, dtype=np.int64)


def cone(radius=0.5, height=1.0, segments=64):
    verts = []
    faces = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts.append([radius * math.cos(a), radius * math.sin(a), 0.0])
    apex = segments
    base_center = segments + 1
    verts.append([0.0, 0.0, height])
    verts.append([0.0, 0.0, 0.0])
    for i in range(segments):
        j = (i + 1) % segments
        faces.append([apex, j, i])
        faces.append([base_center, i, j])
    return np.asarray(verts), np.asarray(faces, dtype=np.int64)


def torus(major=0.6, minor=0.25, u_segments=64, v_segments=32):
    verts = []
    faces = []
    for i in range(u_segments):
        th = 2 * math.pi * i / u_segments
        for j in range(v_segments):
            phi = 2 * math.pi * j / v_segments
            r = major + minor * math.cos(phi)
            verts.append([r * math.cos(th), r * math.sin(th), minor * math.sin(phi)])
    for i in range(u_segments):
        i1 = (i + 1) % u_segments
        for j in range(v_segments):
            j1 = (j + 1) % v_segments
            a = i * v_segments + j
            b = i * v_segments + j1
            c = i1 * v_segments + j
            d = i1 * v_segments + j1
            faces.append([a, c, d])
            faces.append([a, d, b])
    return np.asarray(verts), np.asarray(faces, dtype=np.int64)


def main():
    out = Path(__file__).resolve().parent
    for name, (v, f) in {
        "box": box(),
        "cylinder": cylinder(),
        "sphere": sphere(),
        "cone": cone(),
        "torus": torus(),
    }.items():
        v, f = weld(v, f)
        v, f = ensure_outward(v, f)
        v, f = fix_winding(v, f)
        path = out / f"{name}.stl"
        stl_io.write_stl(str(path), v, f)
        print(f"{path}  ({len(v)} verts, {len(f)} faces)")


def weld(vertices, faces, decimals=6):
    rounded = np.round(vertices, decimals)
    _, inverse = np.unique(rounded, axis=0, return_inverse=True)
    unique_idx, first = np.unique(inverse, return_index=True)
    order = np.argsort(unique_idx)
    remap = order[np.argsort(unique_idx)]
    return vertices[first], remap[inverse[faces]].astype(np.int64)


def ensure_outward(vertices, faces):
    """Flip winding so the mesh has a positive signed volume."""
    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    vol = np.einsum("ij,ij->", a, np.cross(b, c))
    if vol < 0:
        faces = faces[:, [0, 2, 1]]
    return vertices, faces


def fix_winding(vertices, faces):
    """BFS propagation that makes every face consistently outward-oriented."""
    from collections import defaultdict

    edge_map = defaultdict(list)
    for fi, (a, b, c) in enumerate(faces):
        for u, v in ((a, b), (b, c), (c, a)):
            edge_map[tuple(sorted((u, v)))].append((fi, (u, v)))

    flip = np.zeros(len(faces), dtype=bool)
    seen = np.zeros(len(faces), dtype=bool)
    stack = [0]
    seen[0] = True
    while stack:
        fi = stack.pop()
        a, b, c = (int(x) for x in faces[fi])
        for u, v in ((a, b), (b, c), (c, a)):
            key = tuple(sorted((u, v)))
            for fj, (fu, fv) in edge_map[key]:
                if seen[fj]:
                    continue
                seen[fj] = True
                # consistent neighbours traverse the shared edge in opposite
                # directions; same direction means we must flip this face
                if (fu, fv) == (u, v):
                    flip[fj] = True
                stack.append(fj)

    out = faces.copy()
    out[flip] = out[flip][:, [0, 2, 1]]
    return vertices, out


if __name__ == "__main__":
    main()
