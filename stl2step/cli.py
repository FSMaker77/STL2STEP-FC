"""Command-line interface (headless conversion for automation and batch jobs)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.params import ConversionParams
from .profiles import load_all, load_by_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stl2step",
        description="Convert STL meshes into editable STEP models.",
    )
    parser.add_argument("inputs", nargs="*", help="file STL o cartelle da convertire")
    parser.add_argument("-o", "--output", help="cartella di output (default: accanto al sorgente)")
    parser.add_argument(
        "-m",
        "--mode",
        choices=["auto", "parametric", "tessellated"],
        default=None,
        help="modalità di conversione (default: dal profilo)",
    )
    parser.add_argument("-p", "--profile", help="profilo di conversione (id)")
    parser.add_argument("--list-profiles", action="store_true", help="elenca i profili disponibili")
    parser.add_argument(
        "--angle", type=float, default=None, help="tolleranza angolare in gradi"
    )
    parser.add_argument(
        "--distance", type=float, default=None, help="tolleranza di distanza"
    )
    args = parser.parse_args(argv)

    profiles = load_all()
    if args.list_profiles:
        for p in profiles:
            print(f"{p.id:16s} {p.name:20s} {p.description}")
        return 0

    params = ConversionParams()
    if args.profile:
        profile = load_by_id(args.profile)
        if profile is None:
            print(f"Profilo sconosciuto: {args.profile}", file=sys.stderr)
            return 2
        params = profile.to_params()
    if args.mode:
        params.mode = args.mode
    if args.angle is not None:
        params.angular_tolerance_deg = args.angle
    if args.distance is not None:
        params.distance_tolerance = args.distance

    files: list[Path] = []
    for inp in args.inputs:
        p = Path(inp)
        if p.is_dir():
            files.extend(sorted(list(p.glob("*.stl")) + list(p.glob("*.STL"))))
        elif p.suffix.lower() == ".stl":
            files.append(p)
        else:
            print(f"Ignorato (non è un .stl): {inp}", file=sys.stderr)

    if not files:
        print("Nessun file STL trovato.", file=sys.stderr)
        return 1

    out_dir = Path(args.output) if args.output else None
    # Imported lazily so --help/--list-profiles stay fast.
    from .core.convert import convert_stl_to_step
    ok = 0
    for src in files:
        dst = (out_dir / f"{src.stem}.step") if out_dir else src.with_suffix(".step")
        try:
            result = convert_stl_to_step(str(src), str(dst), params)
            if result.mode_used == "parametric":
                detail = (
                    f"{result.n_planar} piani, {result.n_cylinders} cilindri, "
                    f"{result.n_spheres} sfere"
                )
            else:
                detail = "tassellato"
            print(f"✓ {src.name} → {dst.name} ({result.mode_used}, {detail})")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"✗ {src.name}: {exc}", file=sys.stderr)
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
