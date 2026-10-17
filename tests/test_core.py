"""Core engine tests (run with pytest or directly with python)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stl2step.core.convert import ConversionParams, convert_stl_to_step
from stl2step.core.mesh import Mesh

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _run(name: str, mode: str):
    src = SAMPLES / f"{name}.stl"
    dst = Path("/tmp") / f"test_{name}_{mode}.step"
    params = ConversionParams(mode=mode)
    return convert_stl_to_step(str(src), str(dst), params), src


def test_load_and_summary():
    m = Mesh.from_stl(str(SAMPLES / "box.stl"))
    assert m.n_faces == 12
    assert m.is_watertight()
    assert abs(m.volume() - 1.0) < 1e-6


def test_tessellated_box():
    result, _ = _run("box", "tessellated")
    assert result.is_solid
    assert abs(result.solid_volume - 1.0) < 0.05


def test_parametric_cylinder():
    result, _ = _run("cylinder", "parametric")
    assert result.is_solid
    assert result.n_cylinders >= 1
    assert abs(result.solid_volume - 0.785) < 0.05


def test_parametric_box():
    result, _ = _run("box", "parametric")
    assert result.is_solid
    assert abs(result.solid_volume - 1.0) < 0.05


def test_sphere_correct_volume():
    result, _ = _run("sphere", "parametric")
    assert result.is_solid
    assert abs(result.solid_volume - 0.523) < 0.05


def test_sphere_is_parametric():
    """A full sphere must be reconstructed as an analytic solid (single face)."""
    result, src = _run("sphere", "parametric")
    dst = Path("/tmp") / "test_sphere_parametric.step"
    convert_stl_to_step(str(src), str(dst), ConversionParams(mode="parametric"))
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE

    reader = STEPControl_Reader()
    reader.ReadFile(str(dst))
    reader.TransferRoots()
    shape = reader.OneShape()
    nf = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        nf += 1
        ex.Next()
    assert nf == 1  # analytic sphere = one face


def test_parametric_cone():
    """A cone must be reconstructed as an analytic cone + planar base (2 faces)."""
    from stl2step.profiles import load_by_id
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE

    params = load_by_id("mechanical").to_params()
    dst = Path("/tmp") / "test_cone_parametric.step"
    result = convert_stl_to_step(str(SAMPLES / "cone.stl"), str(dst), params)
    assert result.is_solid
    assert result.n_cones >= 1
    assert abs(result.solid_volume - 0.2618) < 0.05

    reader = STEPControl_Reader()
    reader.ReadFile(str(dst))
    reader.TransferRoots()
    shape = reader.OneShape()
    nf = 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        nf += 1
        ex.Next()
    assert nf == 2  # cone side + base


if __name__ == "__main__":
    for fn in (
        test_load_and_summary,
        test_tessellated_box,
        test_parametric_cylinder,
        test_parametric_box,
        test_sphere_correct_volume,
        test_sphere_is_parametric,
        test_parametric_cone,
    ):
        fn()
        print(f"✓ {fn.__name__}")
    print("All tests passed.")
