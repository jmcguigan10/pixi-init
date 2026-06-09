#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from common import manifest_path, pixi_env_path, pixi_path, project_root, run


COMPONENTS = ("clhep", "geant4", "genfit")


def strip_inline_comment(line: str) -> str:
    quote: str | None = None
    out: list[str] = []

    for char in line:
        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            out.append(char)
            continue

        if char == "#" and quote is None:
            break

        out.append(char)

    return "".join(out).rstrip()


def strip_outer_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_flat_config(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}

    for raw_line in path.read_text().splitlines():
        line = strip_inline_comment(raw_line)
        if not line.strip():
            continue

        if ":" not in line:
            raise SystemExit(f"Unsupported line in {path}: {raw_line}")

        key, value = line.split(":", 1)
        key = key.strip()
        value = strip_outer_quotes(value.strip())

        if not key:
            raise SystemExit(f"Empty key in {path}: {raw_line}")

        data[key] = value

    return data


def path_from_config(root: Path, config: dict[str, str], key: str) -> Path:
    value = config[key]
    path = Path(value)
    return path if path.is_absolute() else root / path


def capture(
    cmd: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    rendered = [str(part) for part in cmd]
    print("+", " ".join(rendered))
    result = subprocess.run(
        rendered,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    return result.stdout.strip()


def pixi_run(
    pixi: Path,
    manifest: Path,
    args: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    run([pixi, "run", "--manifest-path", manifest, *args], cwd=cwd, env=env)


def pixi_capture(
    pixi: Path,
    manifest: Path,
    args: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    return capture([pixi, "run", "--manifest-path", manifest, *args], cwd=cwd, env=env)


def safe_extract_tarball(tarball: Path, destination: Path) -> None:
    destination = destination.resolve()

    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(destination) + os.sep):
                raise SystemExit(f"Unsafe path in tarball: {member.name}")

        archive.extractall(destination)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
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


def existing_lib_dirs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[Path] = set()

    for prefix in paths:
        for name in ("lib", "lib64", "lib/root"):
            candidate = prefix / name
            if candidate.exists() and candidate not in seen:
                out.append(candidate)
                seen.add(candidate)

    return out


def existing_env_entries(value: str) -> list[str]:
    entries: list[str] = []

    for entry in value.split(os.pathsep):
        if not entry:
            continue

        path = Path(entry)
        if path.is_absolute() and not path.exists():
            continue

        entries.append(entry)

    return entries


def build_env(root: Path, env_root: Path, prefixes: dict[str, Path]) -> dict[str, str]:
    env = os.environ.copy()
    prefix_values = [
        env_root,
        root / ".local" / "xqilla",
        prefixes["clhep"],
        prefixes["geant4"],
        prefixes["genfit"],
    ]
    bin_values = [env_root / "bin", *(prefix / "bin" for prefix in prefix_values[1:])]
    lib_values = existing_lib_dirs(prefix_values)
    pkg_values = [
        env_root / "lib" / "pkgconfig",
        env_root / "share" / "pkgconfig",
        *(lib_dir / "pkgconfig" for lib_dir in lib_values),
    ]

    env["PATH"] = os.pathsep.join(
        [str(path) for path in bin_values if path.exists()]
        + existing_env_entries(env.get("PATH", ""))
    )
    env["CMAKE_PREFIX_PATH"] = os.pathsep.join(
        [str(path) for path in prefix_values if path.exists()]
        + existing_env_entries(env.get("CMAKE_PREFIX_PATH", ""))
    )
    env["PKG_CONFIG_PATH"] = os.pathsep.join(
        [str(path) for path in pkg_values if path.exists()]
        + existing_env_entries(env.get("PKG_CONFIG_PATH", ""))
    )
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(path) for path in lib_values]
        + existing_env_entries(env.get("LD_LIBRARY_PATH", ""))
    )
    env["DYLD_LIBRARY_PATH"] = os.pathsep.join(
        [str(path) for path in lib_values]
        + existing_env_entries(env.get("DYLD_LIBRARY_PATH", ""))
    )
    env["LIBRARY_PATH"] = os.pathsep.join(
        [str(path) for path in lib_values]
        + existing_env_entries(env.get("LIBRARY_PATH", ""))
    )
    env["ROOTSYS"] = str(env_root)
    env["GENFIT"] = str(prefixes["genfit"])
    env["GIT_TERMINAL_PROMPT"] = "0"

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

    return env


def cmake_prefix_value(paths: list[Path]) -> str:
    return ";".join(str(path) for path in paths if path.exists())


def cmake_rpath_value(paths: list[Path]) -> str:
    rpaths: list[Path] = []
    seen: set[Path] = set()

    for prefix in paths:
        for name in ("lib", "lib64", "lib/root"):
            candidate = prefix / name
            if candidate not in seen:
                rpaths.append(candidate)
                seen.add(candidate)

    return ";".join(str(path) for path in rpaths)


def find_cmake_config(prefix: Path, name: str) -> Path | None:
    candidates = sorted(prefix.rglob(f"{name}Config.cmake"))
    if not candidates:
        return None
    return candidates[0].parent


def find_first(prefix: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(prefix.glob(pattern))
        if matches:
            return matches[0]
    return None


def prepare_git_source(
    component: str,
    source_root: Path,
    config: dict[str, str],
    pixi: Path,
    manifest: Path,
    env: dict[str, str],
) -> Path:
    url = config[f"source.{component}.url"]
    ref = config[f"source.{component}.ref"]
    expected_sha = config[f"source.{component}.sha"]

    if not source_root.exists():
        source_root.parent.mkdir(parents=True, exist_ok=True)
        pixi_run(
            pixi,
            manifest,
            ["git", "clone", "--branch", ref, "--depth", "1", url, source_root],
            env=env,
        )
    elif not (source_root / ".git").exists():
        raise SystemExit(f"Source path exists but is not a git checkout: {source_root}")
    else:
        pixi_run(pixi, manifest, ["git", "fetch", "--force", "origin", ref], cwd=source_root, env=env)

    pixi_run(pixi, manifest, ["git", "checkout", "--force", expected_sha], cwd=source_root, env=env)
    actual_sha = pixi_capture(pixi, manifest, ["git", "rev-parse", "HEAD"], cwd=source_root, env=env)

    if actual_sha != expected_sha:
        raise SystemExit(
            f"{component} checkout mismatch: expected {expected_sha}, got {actual_sha}"
        )

    return source_root


def prepare_tar_source(component: str, src_dir: Path, config: dict[str, str]) -> Path:
    url = config[f"source.{component}.url"]
    source_name = config[f"source.{component}.root"]
    tarball_name = config[f"source.{component}.tarball"]
    source_root = src_dir / source_name
    tarball = src_dir / tarball_name

    if not source_root.exists():
        if not tarball.exists():
            download(url, tarball)
        safe_extract_tarball(tarball, src_dir)

    if not source_root.exists():
        raise SystemExit(f"Expected extracted source directory does not exist: {source_root}")

    return source_root


def cmake_source_dir(source_root: Path, component: str) -> Path:
    if (source_root / "CMakeLists.txt").exists():
        return source_root

    nested = source_root / component
    if (nested / "CMakeLists.txt").exists():
        return nested

    raise SystemExit(f"Could not find CMakeLists.txt under {source_root}")


def common_cmake_args(
    prefix: Path,
    config: dict[str, str],
    cmake_prefixes: list[Path],
    rpath_prefixes: list[Path],
) -> list[str]:
    return [
        f"-DCMAKE_BUILD_TYPE={config['build_type']}",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        f"-DCMAKE_CXX_STANDARD={config['cxx_standard']}",
        "-DCMAKE_CXX_STANDARD_REQUIRED=ON",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
        "-DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON",
        f"-DCMAKE_INSTALL_RPATH={cmake_rpath_value(rpath_prefixes)}",
        f"-DCMAKE_PREFIX_PATH={cmake_prefix_value(cmake_prefixes)}",
    ]


def configure_build_install(
    component: str,
    source_root: Path,
    build_root: Path,
    prefix: Path,
    cmake_args: list[str],
    jobs: str,
    pixi: Path,
    manifest: Path,
    env: dict[str, str],
) -> None:
    source = cmake_source_dir(source_root, component)
    build_root.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)

    pixi_run(
        pixi,
        manifest,
        ["cmake", "-S", source, "-B", build_root, "-G", "Ninja", *cmake_args],
        env=env,
    )
    pixi_run(
        pixi,
        manifest,
        ["cmake", "--build", build_root, "--target", "install", "--parallel", jobs],
        env=env,
    )


def build_clhep(
    source_root: Path,
    build_root: Path,
    prefixes: dict[str, Path],
    config: dict[str, str],
    jobs: str,
    pixi: Path,
    manifest: Path,
    env: dict[str, str],
    env_root: Path,
) -> None:
    args = common_cmake_args(
        prefixes["clhep"],
        config,
        [env_root],
        [prefixes["clhep"]],
    ) + [
        f"-DCLHEP_BUILD_CXXSTD=-std=c++{config['cxx_standard']}",
        "-DCLHEP_BUILD_STATIC_LIBS=OFF",
    ]
    configure_build_install("clhep", source_root, build_root, prefixes["clhep"], args, jobs, pixi, manifest, env)


def build_geant4(
    source_root: Path,
    build_root: Path,
    prefixes: dict[str, Path],
    config: dict[str, str],
    jobs: str,
    pixi: Path,
    manifest: Path,
    env: dict[str, str],
    env_root: Path,
) -> None:
    clhep_dir = find_cmake_config(prefixes["clhep"], "CLHEP") or prefixes["clhep"]
    args = common_cmake_args(
        prefixes["geant4"],
        config,
        [env_root, prefixes["clhep"]],
        [prefixes["clhep"], prefixes["geant4"]],
    ) + [
        "-DGEANT4_BUILD_MULTITHREADED=ON",
        "-DGEANT4_INSTALL_DATA=ON",
        "-DGEANT4_USE_GDML=ON",
        "-DGEANT4_USE_SYSTEM_CLHEP=ON",
        "-DGEANT4_USE_SYSTEM_EXPAT=ON",
        "-DGEANT4_USE_QT=OFF",
        "-DGEANT4_USE_OPENGL_X11=OFF",
        "-DGEANT4_USE_RAYTRACER_X11=OFF",
        f"-DCLHEP_DIR={clhep_dir}",
        f"-DCLHEP_ROOT_DIR={prefixes['clhep']}",
        f"-DXercesC_ROOT={env_root}",
        f"-DXERCESC_ROOT_DIR={env_root}",
    ]
    configure_build_install("geant4", source_root, build_root, prefixes["geant4"], args, jobs, pixi, manifest, env)


def build_genfit(
    source_root: Path,
    build_root: Path,
    prefixes: dict[str, Path],
    config: dict[str, str],
    jobs: str,
    pixi: Path,
    manifest: Path,
    env: dict[str, str],
    env_root: Path,
) -> None:
    root_dir = find_cmake_config(env_root, "ROOT")
    if not root_dir:
        raise SystemExit(f"Missing ROOTConfig.cmake under Pixi environment: {env_root}")

    args = common_cmake_args(
        prefixes["genfit"],
        config,
        [env_root],
        [env_root, prefixes["genfit"]],
    ) + [
        "-DBUILD_TESTING=OFF",
        f"-DROOT_DIR={root_dir}",
    ]
    configure_build_install("genfit", source_root, build_root, prefixes["genfit"], args, jobs, pixi, manifest, env)


def write_state(root: Path, config: dict[str, str], prefixes: dict[str, Path], env_root: Path) -> None:
    state_dir = path_from_config(root, config, "state_dir")
    state_dir.mkdir(parents=True, exist_ok=True)

    cmake_prefixes = [
        env_root,
        root / ".local" / "xqilla",
        prefixes["clhep"],
        prefixes["geant4"],
        prefixes["genfit"],
    ]
    genfit_library = find_first(prefixes["genfit"], [
        "lib/libgenfit2.dylib",
        "lib/libgenfit2.so",
        "lib/libgenfit2.so.*",
        "lib/libgenfit2.a",
        "lib64/libgenfit2.dylib",
        "lib64/libgenfit2.so",
        "lib64/libgenfit2.so.*",
        "lib64/libgenfit2.a",
    ])

    state = {
        "build_type": config["build_type"],
        "cxx_standard": int(config["cxx_standard"]),
        "prefixes": {
            **{name: str(path) for name, path in prefixes.items()},
            "root": str(env_root),
        },
        "cmake_prefix_path": cmake_prefix_value(cmake_prefixes),
        "muse_cmake_hints": [
            f"-DCMAKE_CXX_STANDARD={config['cxx_standard']}",
            f"-DCMAKE_PREFIX_PATH={cmake_prefix_value(cmake_prefixes)}",
        ],
    }

    if genfit_library:
        state["muse_cmake_hints"].extend([
            f"-DGENFIT_INCLUDE_DIR={prefixes['genfit'] / 'include'}",
            f"-DGENFIT_LIBRARY={genfit_library}",
        ])

    output = state_dir / "source-stack.json"
    output.write_text(json.dumps(state, indent=2) + "\n")
    print(f"Wrote source stack state: {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "components",
        nargs="*",
        choices=[*COMPONENTS, "all"],
        default=None,
        help="Components to build in dependency order. Defaults to all.",
    )
    parser.add_argument("--root", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--jobs", default=None)
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else project_root()
    pixi = pixi_path(root)
    manifest = manifest_path(root)
    env_root = pixi_env_path(root)

    config_path = Path(args.config).resolve() if args.config else root / ".install" / "cfgs" / "source-stack.yml"
    config = parse_flat_config(config_path)

    src_dir = path_from_config(root, config, "source_dir")
    build_dir = path_from_config(root, config, "build_dir")
    prefixes = {component: path_from_config(root, config, f"prefix.{component}") for component in COMPONENTS}

    jobs = args.jobs or config["jobs"]
    if jobs == "auto":
        jobs = str(os.cpu_count() or 2)

    deps_script = root / ".install" / "python" / "pixi_add_from_yml.py"
    run([
        sys.executable,
        deps_script,
        root / ".install" / "cfgs" / "add-basic.yml",
        "--root",
        root,
    ])
    run([pixi, "install", "--manifest-path", manifest])

    registrar = root / ".install" / "python" / "register_source_stack_pixi.py"
    run([sys.executable, registrar, "--root", root])

    env = build_env(root, env_root, prefixes)

    requested_components = args.components or ["all"]
    selected = list(COMPONENTS) if "all" in requested_components else [
        component for component in COMPONENTS if component in set(requested_components)
    ]

    src_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    for component in selected:
        print()
        print(f"==> Building {component}")
        source_kind = config[f"source.{component}.kind"]
        source_root = src_dir / component

        if source_kind == "git":
            source_root = prepare_git_source(component, source_root, config, pixi, manifest, env)
        elif source_kind == "tar":
            source_root = prepare_tar_source(component, src_dir, config)
        else:
            raise SystemExit(f"Unsupported source kind for {component}: {source_kind}")

        component_build_dir = build_dir / component

        if component == "clhep":
            build_clhep(source_root, component_build_dir, prefixes, config, jobs, pixi, manifest, env, env_root)
        elif component == "geant4":
            build_geant4(source_root, component_build_dir, prefixes, config, jobs, pixi, manifest, env, env_root)
        elif component == "genfit":
            build_genfit(source_root, component_build_dir, prefixes, config, jobs, pixi, manifest, env, env_root)

        write_state(root, config, prefixes, env_root)

    run([sys.executable, registrar, "--root", root])

    print()
    print("Source stack build finished.")
    print(f"MUSE CMake hints: {path_from_config(root, config, 'state_dir') / 'source-stack.json'}")


if __name__ == "__main__":
    main()
