#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

from common import (
    first_existing,
    manifest_path,
    pixi_env_path,
    pixi_path,
    project_root,
    run,
    try_run,
)


VERSION = "2.3.4"
SOURCE_URL = f"https://sourceforge.net/projects/xqilla/files/XQilla-{VERSION}.tar.gz/download"


def safe_extract_tarball(tarball: Path, destination: Path) -> None:
    destination = destination.resolve()

    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(destination) + os.sep):
                raise SystemExit(f"Unsafe path in tarball: {member.name}")

        archive.extractall(destination)


def download(url: str, destination: Path) -> None:
    print(f"Downloading {url}")
    print(f"       to {destination}")

    with urllib.request.urlopen(url) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def find_compiler(env_root: Path, names: list[str]) -> Path | None:
    bindir = env_root / "bin"
    return first_existing([bindir / name for name in names])


def main() -> None:
    root = project_root()
    pixi = pixi_path(root)
    manifest = manifest_path(root)
    env_root = pixi_env_path(root)

    src_dir = root / ".install" / "src"
    source_root = src_dir / f"XQilla-{VERSION}"
    prefix = root / ".local" / "xqilla"

    src_dir.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)

    tarball_candidates = [
        src_dir / f"XQilla-{VERSION}.tar.gz",
        src_dir / f"xqilla-{VERSION}.tar.gz",
        src_dir / "xqilla.tar.gz",
    ]

    tarball = first_existing(tarball_candidates) or tarball_candidates[0]

    if not source_root.exists():
        if not tarball.exists():
            download(SOURCE_URL, tarball)

        safe_extract_tarball(tarball, src_dir)

    if not source_root.exists():
        raise SystemExit(f"Expected source directory does not exist: {source_root}")

    run([
        pixi,
        "install",
        "--manifest-path",
        manifest,
    ])

    patcher = root / ".install" / "python" / "patch_xqilla_gcc.py"
    run([
        sys.executable,
        patcher,
        source_root,
    ])

    registrar = root / ".install" / "python" / "register_xqilla_pixi.py"
    run([
        sys.executable,
        registrar,
        "--root",
        root,
    ])

    if (source_root / "Makefile").exists():
        try_run([
            pixi,
            "run",
            "--manifest-path",
            manifest,
            "make",
            "distclean",
        ], cwd=source_root)

    env = os.environ.copy()

    env["CPPFLAGS"] = f"-I{env_root}/include"
    env["LDFLAGS"] = f"-L{env_root}/lib"
    env["CFLAGS"] = "-O2"
    env["CXXFLAGS"] = "-O2 -std=gnu++14"
    env["PKG_CONFIG_PATH"] = (
        f"{env_root}/lib/pkgconfig:"
        f"{env_root}/share/pkgconfig:"
        f"{env.get('PKG_CONFIG_PATH', '')}"
    )
    env["LD_LIBRARY_PATH"] = f"{env_root}/lib:{env.get('LD_LIBRARY_PATH', '')}"

    cc = find_compiler(env_root, [
        "x86_64-conda-linux-gnu-cc",
        "x86_64-conda-linux-gnu-gcc",
        "gcc",
        "cc",
    ])

    cxx = find_compiler(env_root, [
        "x86_64-conda-linux-gnu-c++",
        "x86_64-conda-linux-gnu-g++",
        "g++",
        "c++",
    ])

    if cc:
        env["CC"] = str(cc)

    if cxx:
        env["CXX"] = str(cxx)

    run([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        "./configure",
        f"--prefix={prefix}",
        f"--with-xerces={env_root}",
    ], cwd=source_root, env=env)

    jobs = str(os.cpu_count() or 2)

    run([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        "make",
        f"-j{jobs}",
    ], cwd=source_root, env=env)

    run([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        "make",
        "install",
    ], cwd=source_root, env=env)

    print()
    print(f"Installed XQilla to: {prefix}")
    print(f"Binary: {prefix / 'bin' / 'xqilla'}")


if __name__ == "__main__":
    main()