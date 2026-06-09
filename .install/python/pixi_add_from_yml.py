#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import platform as platform_module
import re
from pathlib import Path

from common import manifest_path, pixi_path, project_root, run


SECTION_ALIASES = {
    "dependencies": "dependencies",
    "conda": "dependencies",
    "pypi": "pypi",
    "pypi-dependencies": "pypi",
}


@dataclass
class DependencyConfig:
    dependencies: list[str] = field(default_factory=list)
    pypi: list[str] = field(default_factory=list)
    target_dependencies: dict[str, list[str]] = field(default_factory=dict)
    target_pypi: dict[str, list[str]] = field(default_factory=dict)


def detect_platform() -> str:
    system = platform_module.system()
    machine = platform_module.machine().lower()

    if system == "Linux" and machine in {"x86_64", "amd64"}:
        return "linux-64"
    if system == "Linux" and machine in {"aarch64", "arm64"}:
        return "linux-aarch64"
    if system == "Darwin" and machine in {"x86_64", "amd64"}:
        return "osx-64"
    if system == "Darwin" and machine == "arm64":
        return "osx-arm64"

    raise SystemExit(f"Unsupported platform: {system}:{machine}")


def parse_section(section: str) -> tuple[str, str | None] | None:
    kind = SECTION_ALIASES.get(section)
    if kind:
        return kind, None

    target_match = re.match(
        r"^target\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$",
        section,
    )
    if not target_match:
        return None

    target_platform = target_match.group(1)
    target_kind = SECTION_ALIASES.get(target_match.group(2))
    if not target_kind:
        return None

    return target_kind, target_platform


def strip_inline_comment(line: str) -> str:
    # Simple config parser, not a full YAML parser.
    # Good enough for:
    #   dependencies:
    #     - python=3.12
    #     - "cmake>=3.30"
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


def parse_simple_yml(path: Path) -> DependencyConfig:
    data = DependencyConfig()

    current: tuple[str, str | None] | None = None

    for raw_line in path.read_text().splitlines():
        line = strip_inline_comment(raw_line)

        if not line.strip():
            continue

        section_match = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*$", line)
        if section_match:
            original = section_match.group(1)
            current = parse_section(original)
            if current is None:
                raise SystemExit(f"Unsupported section in {path}: {original}")
            continue

        item_match = re.match(r"^\s*-\s*(.+?)\s*$", line)
        if item_match and current:
            item = strip_outer_quotes(item_match.group(1))
            if item:
                kind, target_platform = current
                if target_platform:
                    target_data = (
                        data.target_dependencies
                        if kind == "dependencies"
                        else data.target_pypi
                    )
                    target_data.setdefault(target_platform, []).append(item)
                elif kind == "dependencies":
                    data.dependencies.append(item)
                else:
                    data.pypi.append(item)
            continue

        raise SystemExit(
            f"Unsupported line in {path}:\n"
            f"  {raw_line}\n\n"
            "This parser intentionally supports only simple list sections."
        )

    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "config",
        nargs="?",
        default=None,
        help="Path to add-basic.yml",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--platform",
        default=None,
        help="Current Pixi platform. Defaults to auto-detection.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else project_root()
    pixi = pixi_path(root)
    manifest = manifest_path(root)
    platform = args.platform or detect_platform()

    config = Path(args.config).resolve() if args.config else root / ".install" / "cfgs" / "add-basic.yml"
    if not config.exists():
        raise SystemExit(f"Missing config file: {config}")

    parsed = parse_simple_yml(config)
    dependencies = parsed.dependencies
    pypi_dependencies = parsed.pypi
    target_dependencies = parsed.target_dependencies.get(platform, [])
    target_pypi_dependencies = parsed.target_pypi.get(platform, [])

    if dependencies:
        run([
            pixi,
            "add",
            "--manifest-path",
            manifest,
            *dependencies,
        ])
    else:
        print("No conda dependencies listed.")

    if target_dependencies:
        run([
            pixi,
            "add",
            "--manifest-path",
            manifest,
            "--platform",
            platform,
            *target_dependencies,
        ])
    else:
        print(f"No platform-specific conda dependencies listed for {platform}.")

    if pypi_dependencies:
        run([
            pixi,
            "add",
            "--manifest-path",
            manifest,
            "--pypi",
            *pypi_dependencies,
        ])
    else:
        print("No PyPI dependencies listed.")

    if target_pypi_dependencies:
        run([
            pixi,
            "add",
            "--manifest-path",
            manifest,
            "--platform",
            platform,
            "--pypi",
            *target_pypi_dependencies,
        ])
    else:
        print(f"No platform-specific PyPI dependencies listed for {platform}.")


if __name__ == "__main__":
    main()
