#!/usr/bin/env python3
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

from common import manifest_path, pixi_env_path, pixi_path, project_root
from build_source_stack import find_cmake_config, find_first, parse_flat_config, path_from_config


COMPONENTS = ("clhep", "geant4", "genfit")


def capture(cmd: list[str | Path]) -> str:
    rendered = [str(part) for part in cmd]
    print("+", shlex.join(rendered))
    result = subprocess.run(
        rendered,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout.rstrip())
        raise subprocess.CalledProcessError(
            result.returncode,
            rendered,
            output=result.stdout,
            stderr=result.stderr,
        )

    output = result.stdout.strip()
    if output:
        print(output)
    return output


def require_path(path: Path, description: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {description}: {path}")
    print(f"Found {description}: {path}")


def verify_dynamic_links(path: Path) -> None:
    if sys.platform.startswith("linux"):
        result = subprocess.run(
            ["ldd", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        print(result.stdout)
        if "not found" in result.stdout:
            raise SystemExit(f"Dynamic library check failed for {path}")
    elif sys.platform == "darwin":
        result = subprocess.run(
            ["otool", "-L", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        print(result.stdout)


def main() -> None:
    root = project_root()
    pixi = pixi_path(root)
    manifest = manifest_path(root)
    root_prefix = pixi_env_path(root)
    config = parse_flat_config(root / ".install" / "cfgs" / "source-stack.yml")
    prefixes = {component: path_from_config(root, config, f"prefix.{component}") for component in COMPONENTS}
    state_path = path_from_config(root, config, "state_dir") / "source-stack.json"

    require_path(prefixes["clhep"], "CLHEP prefix")
    clhep_config = find_cmake_config(prefixes["clhep"], "CLHEP")
    if not clhep_config:
        raise SystemExit(f"Missing CLHEPConfig.cmake under {prefixes['clhep']}")
    print(f"Found CLHEP CMake config: {clhep_config}")

    require_path(prefixes["geant4"], "Geant4 prefix")
    geant4_config = find_cmake_config(prefixes["geant4"], "Geant4")
    if not geant4_config:
        raise SystemExit(f"Missing Geant4Config.cmake under {prefixes['geant4']}")
    print(f"Found Geant4 CMake config: {geant4_config}")
    geant4_library = find_first(prefixes["geant4"], [
        "lib/libG4run.dylib",
        "lib/libG4run.so",
        "lib/libG4run.so.*",
        "lib64/libG4run.dylib",
        "lib64/libG4run.so",
        "lib64/libG4run.so.*",
    ])
    if not geant4_library:
        raise SystemExit(f"Missing Geant4 runtime library under {prefixes['geant4']}")
    print(f"Found Geant4 runtime library: {geant4_library}")

    geant4_config_bin = prefixes["geant4"] / "bin" / "geant4-config"
    require_path(geant4_config_bin, "geant4-config")
    geant4_version = capture([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        geant4_config_bin,
        "--version",
    ])
    if geant4_version.strip() != "11.4.1":
        raise SystemExit(f"Expected Geant4 11.4.1, got {geant4_version}")

    require_path(root_prefix, "Pixi ROOT prefix")
    root_cmake_config = find_cmake_config(root_prefix, "ROOT")
    if not root_cmake_config:
        raise SystemExit(f"Missing ROOTConfig.cmake under {root_prefix}")
    print(f"Found ROOT CMake config: {root_cmake_config}")

    root_config = root_prefix / "bin" / "root-config"
    require_path(root_config, "root-config")
    root_version = capture([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        root_config,
        "--version",
    ])
    if root_version.strip() != "6.36.10":
        raise SystemExit(f"Expected ROOT 6.36.10, got {root_version}")

    root_features = capture([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        root_config,
        "--features",
    ])
    for feature in ("xml", "gdml"):
        if feature not in root_features.split():
            raise SystemExit(f"ROOT feature missing: {feature}")
    minuit2_library = find_first(root_prefix, [
        "lib/libMinuit2.dylib",
        "lib/libMinuit2.so",
        "lib/libMinuit2.so.*",
        "lib/root/libMinuit2.dylib",
        "lib/root/libMinuit2.so",
        "lib/root/libMinuit2.so.*",
        "lib64/libMinuit2.dylib",
        "lib64/libMinuit2.so",
        "lib64/libMinuit2.so.*",
    ])
    if not minuit2_library:
        raise SystemExit(f"Missing ROOT Minuit2 library under {root_prefix}")
    print(f"Found ROOT Minuit2 library: {minuit2_library}")

    require_path(prefixes["genfit"], "GenFit prefix")
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
    if not genfit_library:
        raise SystemExit(f"Missing GenFit library under {prefixes['genfit']}")
    print(f"Found GenFit library: {genfit_library}")
    require_path(prefixes["genfit"] / "include", "GenFit include directory")

    for candidate in [
        geant4_library,
        root_prefix / "bin" / "root",
        genfit_library,
    ]:
        if candidate.exists():
            verify_dynamic_links(candidate)

    require_path(state_path, "source stack state")
    state = json.loads(state_path.read_text())
    print("MUSE CMake hints:")
    for hint in state.get("muse_cmake_hints", []):
        print(f"  {hint}")

    print("Source stack verification passed.")


if __name__ == "__main__":
    main()
