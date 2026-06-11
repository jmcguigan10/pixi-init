#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
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

    for name in names:
        if "*" in name:
            matches = sorted(path for path in bindir.glob(name) if path.is_file())
            if matches:
                return matches[0]
            continue

        candidate = bindir / name
        if candidate.exists():
            return candidate

    return None


def refresh_autotools_config(source_root: Path, env_root: Path) -> None:
    gnuconfig_dir = env_root / "share" / "gnuconfig"
    autotools_dir = source_root / "autotools"

    for name in ["config.guess", "config.sub"]:
        source = gnuconfig_dir / name
        destination = autotools_dir / name

        if not destination.exists():
            continue

        if not source.exists():
            raise SystemExit(
                f"Missing modern {name}: {source}. "
                "Ensure the gnuconfig Pixi dependency is installed."
            )

        shutil.copy2(source, destination)
        print(f"Refreshed Autotools platform helper: {destination}")


def mach_o_rpaths(path: Path) -> set[str]:
    result = subprocess.run(
        ["otool", "-l", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )

    rpaths: set[str] = set()
    lines = result.stdout.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "cmd LC_RPATH":
            continue

        for candidate in lines[index + 1:index + 6]:
            stripped = candidate.strip()
            if stripped.startswith("path "):
                rpaths.add(stripped.split()[1])
                break

    return rpaths


def add_macos_rpaths(prefix: Path, env_root: Path) -> None:
    if sys.platform != "darwin":
        return

    tool = shutil.which("install_name_tool")
    if not tool:
        raise SystemExit("Missing install_name_tool, which is required on macOS.")

    targets = [prefix / "bin" / "xqilla"]
    targets.extend(sorted((prefix / "lib").glob("*.dylib")))

    for target in targets:
        if not target.exists():
            continue

        existing = mach_o_rpaths(target)
        for rpath in [str(env_root / "lib"), str(prefix / "lib")]:
            if rpath in existing:
                continue

            run([
                tool,
                "-add_rpath",
                rpath,
                target,
            ])
            existing.add(rpath)


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

    refresh_autotools_config(source_root, env_root)

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
    env["LD_LIBRARY_PATH"] = (
        f"{prefix}/lib:{env_root}/lib:{env.get('LD_LIBRARY_PATH', '')}"
    )
    env["DYLD_LIBRARY_PATH"] = (
        f"{prefix}/lib:{env_root}/lib:{env.get('DYLD_LIBRARY_PATH', '')}"
    )

    cc = find_compiler(env_root, [
        "x86_64-conda-linux-gnu-cc",
        "x86_64-conda-linux-gnu-gcc",
        "aarch64-conda-linux-gnu-cc",
        "aarch64-conda-linux-gnu-gcc",
        "arm64-apple-darwin*-clang",
        "x86_64-apple-darwin*-clang",
        "clang",
        "gcc",
        "cc",
    ])

    cxx = find_compiler(env_root, [
        "x86_64-conda-linux-gnu-c++",
        "x86_64-conda-linux-gnu-g++",
        "aarch64-conda-linux-gnu-c++",
        "aarch64-conda-linux-gnu-g++",
        "arm64-apple-darwin*-clang++",
        "x86_64-apple-darwin*-clang++",
        "clang++",
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

    add_macos_rpaths(prefix, env_root)

    print()
    print(f"Installed XQilla to: {prefix}")
    print(f"Binary: {prefix / 'bin' / 'xqilla'}")


if __name__ == "__main__":
    main()
