#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import manifest_path, project_root


TASKS = {
    "source-stack": '"$PIXI_PROJECT_ROOT/.install/shell/build-source-stack.sh"',
    "verify-source-stack": '"$PIXI_PROJECT_ROOT/.install/shell/verify-source-stack.sh"',
    "register-source-stack": '"$PIXI_PROJECT_ROOT/.install/shell/register-source-stack-pixi.sh"',
}


def find_cmake_config(prefix: Path, name: str) -> Path:
    candidates = sorted(prefix.rglob(f"{name}Config.cmake")) if prefix.exists() else []
    return candidates[0].parent if candidates else prefix


def env_path(root: Path, path: Path) -> str:
    resolved = path.resolve()

    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError:
        return str(resolved)

    return "$PIXI_PROJECT_ROOT/" + relative.as_posix()


def quote_env(value: str) -> str:
    return '"' + value + '"'


def activation_env(root: Path) -> dict[str, str]:
    prefixes = {
        "clhep": root / ".local" / "clhep",
        "geant4": root / ".local" / "geant4",
        "genfit": root / ".local" / "genfit",
        "xqilla": root / ".local" / "xqilla",
        "pixi": root / ".pixi" / "envs" / "default",
    }
    bin_paths = [
        prefixes["pixi"] / "bin",
        prefixes["geant4"] / "bin",
        prefixes["clhep"] / "bin",
        prefixes["genfit"] / "bin",
        prefixes["xqilla"] / "bin",
    ]
    lib_paths = [
        prefixes["pixi"] / "lib",
        prefixes["pixi"] / "lib" / "root",
        prefixes["geant4"] / "lib",
        prefixes["geant4"] / "lib64",
        prefixes["clhep"] / "lib",
        prefixes["clhep"] / "lib64",
        prefixes["genfit"] / "lib",
        prefixes["genfit"] / "lib64",
        prefixes["xqilla"] / "lib",
    ]
    include_paths = [
        prefixes["pixi"] / "include",
        prefixes["pixi"] / "include" / "root",
        prefixes["geant4"] / "include",
        prefixes["clhep"] / "include",
        prefixes["genfit"] / "include",
        prefixes["xqilla"] / "include",
    ]
    cmake_prefixes = [
        prefixes["pixi"],
        prefixes["geant4"],
        prefixes["clhep"],
        prefixes["genfit"],
        prefixes["xqilla"],
    ]

    existing_bin_paths = [path for path in bin_paths if path.exists()]
    existing_lib_paths = [path for path in lib_paths if path.exists()]
    existing_include_paths = [path for path in include_paths if path.exists()]
    existing_cmake_prefixes = [path for path in cmake_prefixes if path.exists()]

    path_value = ":".join([env_path(root, path) for path in existing_bin_paths] + ["$PATH"])
    lib_value = ":".join(env_path(root, path) for path in existing_lib_paths)
    include_value = ":".join(
        [env_path(root, path) for path in existing_include_paths] + ["$CPATH"]
    )
    cmake_prefix_value = ":".join(
        [env_path(root, path) for path in existing_cmake_prefixes] + ["$CMAKE_PREFIX_PATH"]
    )

    library_path = f"{lib_value}:$LIBRARY_PATH" if lib_value else "$LIBRARY_PATH"

    return {
        "PATH": quote_env(path_value),
        "CPATH": quote_env(include_value),
        "LIBRARY_PATH": quote_env(library_path),
        "CMAKE_PREFIX_PATH": quote_env(cmake_prefix_value),
        "ROOTSYS": quote_env(env_path(root, prefixes["pixi"])),
        "CLHEP_DIR": quote_env(env_path(root, find_cmake_config(prefixes["clhep"], "CLHEP"))),
        "Geant4_DIR": quote_env(env_path(root, find_cmake_config(prefixes["geant4"], "Geant4"))),
        "ROOT_DIR": quote_env(env_path(root, find_cmake_config(prefixes["pixi"], "ROOT"))),
        "GENFIT": quote_env(env_path(root, prefixes["genfit"])),
    }


def ensure_section(text: str, section: str) -> str:
    header = f"[{section}]"

    if re.search(rf"(?m)^\[{re.escape(section)}\]\s*$", text):
        return text

    if not text.endswith("\n"):
        text += "\n"

    return text + f"\n{header}\n"


def upsert_key(text: str, section: str, key: str, value: str) -> str:
    header_pattern = rf"(?m)^\[{re.escape(section)}\]\s*$"
    header_match = re.search(header_pattern, text)

    if not header_match:
        raise RuntimeError(f"Missing section [{section}]")

    start = header_match.end()
    next_section = re.search(r"(?m)^\[[^\]]+\]\s*$", text[start:])
    end = start + next_section.start() if next_section else len(text)

    before = text[:start]
    body = text[start:end]
    after = text[end:]

    line = f"{key} = {value}"
    key_pattern = rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=.*$"

    if re.search(key_pattern, body):
        body = re.sub(key_pattern, line, body)
    else:
        if body and not body.endswith("\n"):
            body += "\n"
        body += line + "\n"

    return before + body + after


def remove_managed_key(text: str, section: str, key: str) -> str:
    header_pattern = rf"(?m)^\[{re.escape(section)}\]\s*$"
    header_match = re.search(header_pattern, text)

    if not header_match:
        return text

    start = header_match.end()
    next_section = re.search(r"(?m)^\[[^\]]+\]\s*$", text[start:])
    end = start + next_section.start() if next_section else len(text)

    before = text[:start]
    body = text[start:end]
    after = text[end:]
    key_pattern = rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=.*\$PIXI_PROJECT_ROOT.*\n?"
    body = re.sub(key_pattern, "", body)

    return before + body + after


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else project_root()
    manifest = manifest_path(root)

    text = manifest.read_text()

    text = ensure_section(text, "activation.env")
    for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        text = remove_managed_key(text, "activation.env", key)
    for key, value in activation_env(root).items():
        text = upsert_key(text, "activation.env", key, value)

    text = ensure_section(text, "tasks")
    for key, value in TASKS.items():
        text = upsert_key(text, "tasks", key, value)

    manifest.write_text(text)
    print(f"Registered source-stack tasks and environment in {manifest}")


if __name__ == "__main__":
    main()
