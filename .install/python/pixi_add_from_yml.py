#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import manifest_path, pixi_path, project_root, run


SECTION_ALIASES = {
    "dependencies": "dependencies",
    "conda": "dependencies",
    "pypi": "pypi",
    "pypi-dependencies": "pypi",
}


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


def parse_simple_yml(path: Path) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {
        "dependencies": [],
        "pypi": [],
    }

    current: str | None = None

    for raw_line in path.read_text().splitlines():
        line = strip_inline_comment(raw_line)

        if not line.strip():
            continue

        section_match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*$", line)
        if section_match:
            original = section_match.group(1)
            current = SECTION_ALIASES.get(original)
            continue

        item_match = re.match(r"^\s*-\s*(.+?)\s*$", line)
        if item_match and current:
            item = strip_outer_quotes(item_match.group(1))
            if item:
                data.setdefault(current, []).append(item)
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
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else project_root()
    pixi = pixi_path(root)
    manifest = manifest_path(root)

    config = Path(args.config).resolve() if args.config else root / ".install" / "cfgs" / "add-basic.yml"
    if not config.exists():
        raise SystemExit(f"Missing config file: {config}")

    parsed = parse_simple_yml(config)
    dependencies = parsed.get("dependencies", [])
    pypi_dependencies = parsed.get("pypi", [])

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


if __name__ == "__main__":
    main()