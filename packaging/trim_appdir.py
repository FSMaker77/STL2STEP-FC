#!/usr/bin/env python3
"""Copy only the Python packages and shared libraries needed by STL2STEP."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys


def run_ldd(path: str) -> list[str]:
    try:
        out = subprocess.run(
            ["ldd", path], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return []
    result = []
    for line in out.splitlines():
        line = line.strip()
        if "=>" in line:
            target = line.split("=>", 1)[1].strip().split(" ")[0].rstrip(":")
            if target.startswith("/") and os.path.exists(target):
                result.append(target)
        elif line.startswith("/"):
            target = line.split(" ")[0].rstrip(":")
            if os.path.exists(target):
                result.append(target)
    return result


def copy_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: str, dst: str, ignore=None) -> None:
    if not os.path.isdir(src):
        return
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)


def main() -> int:
    if len(sys.argv) != 5:
        print(
            "usage: trim_appdir.py APPDIR SITEPACKAGES PYVER REPO",
            file=sys.stderr,
        )
        return 2
    appdir, sitepkg, pyver, repo = sys.argv[1:]
    target = os.path.join(appdir, "usr", "lib", f"python{pyver}", "site-packages")
    os.makedirs(target, exist_ok=True)

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.pyi")

    # The application and the direct Python dependencies.
    copy_tree(os.path.join(repo, "stl2step"), os.path.join(target, "stl2step"), ignore)
    for name in ("numpy", "numpy.libs", "scipy", "scipy.libs"):
        copy_tree(os.path.join(sitepkg, name), os.path.join(target, name), ignore)

    # OCP Python package.
    ocp_src = os.path.join(sitepkg, "OCP")
    ocp_dst = os.path.join(target, "OCP")
    copy_tree(ocp_src, ocp_dst, ignore)

    ocp_so = glob.glob(os.path.join(ocp_src, "OCP*.so"))
    if not ocp_so:
        print("OCP extension .so not found", file=sys.stderr)
        return 1

    needed = set()
    queue = [ocp_so[0]]
    seen = set()
    while queue:
        path = queue.pop()
        key = os.path.abspath(path)
        if key in seen:
            continue
        seen.add(key)
        for dep in run_ldd(path):
            dependency = os.path.realpath(dep)
            if dependency in seen:
                continue
            if dependency.startswith(os.path.abspath(sitepkg) + os.sep):
                needed.add(dependency)
                queue.append(dependency)

    vtk_dir = os.path.join(target, "vtkmodules")
    cq_dir = os.path.join(target, "cadquery_ocp.libs")
    os.makedirs(vtk_dir, exist_ok=True)
    os.makedirs(cq_dir, exist_ok=True)
    for path in sorted(needed):
        base = os.path.basename(path)
        if f"{os.sep}vtkmodules{os.sep}" in path:
            dst = os.path.join(vtk_dir, base)
        elif f"{os.sep}cadquery_ocp.libs{os.sep}" in path:
            dst = os.path.join(cq_dir, base)
        elif f"{os.sep}OCP{os.sep}" in path:
            dst = os.path.join(ocp_dst, base)
        else:
            continue
        copy_file(path, dst)

    # Strip debug/symbol tables from the VTK shared objects. They are not
    # needed at runtime and are the largest unstripped binaries in the bundle.
    for path in glob.glob(os.path.join(vtk_dir, "*.so*")):
        subprocess.run(
            ["strip", "--strip-unneeded", path],
            capture_output=True,
            check=False,
        )

    # PySide6: only the Qt modules used by the GUI and the Qt libraries they
    # need, plus a small set of platform/image plugins.
    ps_src = os.path.join(sitepkg, "PySide6")
    ps_dst = os.path.join(target, "PySide6")
    for name in (
        "__init__.py",
        "_config.py",
        "_git_pyside_version.py",
        "py.typed",
        "libpyside6.abi3.so.6.12",
        "QtCore.abi3.so",
        "QtGui.abi3.so",
        "QtWidgets.abi3.so",
        "QtOpenGL.abi3.so",
        "QtOpenGLWidgets.abi3.so",
    ):
        src = os.path.join(ps_src, name)
        if os.path.exists(src):
            copy_file(src, os.path.join(ps_dst, name))

    plugins = [
        "platforms/libqxcb.so",
        "platforms/libqoffscreen.so",
        "platforms/libqwayland.so",
        "xcbglintegrations/libqxcb-glx-integration.so",
        "xcbglintegrations/libqxcb-egl-integration.so",
        "imageformats/libqico.so",
        "imageformats/libqjpeg.so",
        "imageformats/libqgif.so",
        "imageformats/libqsvg.so",
        "iconengines/libqsvgicon.so",
        "platforminputcontexts/libcomposeplatforminputcontextplugin.so",
        "platforminputcontexts/libibusplatforminputcontextplugin.so",
    ]
    for sub in (
        "wayland-decoration-client",
        "wayland-graphics-integration-client",
        "wayland-shell-integration",
    ):
        directory = os.path.join(ps_src, "Qt", "plugins", sub)
        if os.path.isdir(directory):
            for name in os.listdir(directory):
                if name.endswith(".so"):
                    plugins.append(f"{sub}/{name}")
    for rel in plugins:
        src = os.path.join(ps_src, "Qt", "plugins", rel)
        if os.path.exists(src):
            copy_file(src, os.path.join(ps_dst, "Qt", "plugins", rel))

    # Resolve the Qt shared libraries required by the Python modules and the
    # selected plugins.
    # Resolve from the source tree: ldd needs the wheel's Qt/lib directory to
    # resolve the Qt private-API libraries through RPATH/RUNPATH.
    starts = [
        os.path.join(ps_src, name)
        for name in (
            "libpyside6.abi3.so.6.12",
            "QtCore.abi3.so",
            "QtGui.abi3.so",
            "QtWidgets.abi3.so",
            "QtOpenGL.abi3.so",
            "QtOpenGLWidgets.abi3.so",
        )
    ]
    starts += [
        os.path.join(ps_src, "Qt", "plugins", rel)
        for rel in plugins
        if os.path.exists(os.path.join(ps_src, "Qt", "plugins", rel))
    ]
    q = list(starts)
    seen.clear()
    while q:
        path = q.pop()
        key = os.path.abspath(path)
        if key in seen:
            continue
        seen.add(key)
        for dep in run_ldd(path):
            dependency = os.path.realpath(dep)
            if dependency in seen:
                continue
            if dependency.startswith(os.path.abspath(ps_src) + os.sep):
                rel = os.path.relpath(dependency, ps_src)
                dst = os.path.join(ps_dst, rel)
                if not os.path.exists(dst):
                    copy_file(dependency, dst)
                q.append(dependency)

    # shiboken6 runtime
    copy_tree(os.path.join(sitepkg, "shiboken6"), os.path.join(target, "shiboken6"), ignore)

    # Remove Python caches that may have been copied with the packages.
    for root, dirs, files in os.walk(target):
        for name in list(dirs):
            if name == "__pycache__":
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
                dirs.remove(name)
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
