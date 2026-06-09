#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import manifest_path, project_root


ACTIVATION_ENV = {
    "PATH": '"$PIXI_PROJECT_ROOT/.local/xqilla/bin:$PATH"',
    "LD_LIBRARY_PATH": '"$PIXI_PROJECT_ROOT/.local/xqilla/lib:$PIXI_PROJECT_ROOT/.pixi/envs/default/lib:$LD_LIBRARY_PATH"',
    "DYLD_LIBRARY_PATH": '"$PIXI_PROJECT_ROOT/.local/xqilla/lib:$PIXI_PROJECT_ROOT/.pixi/envs/default/lib:$DYLD_LIBRARY_PATH"',
    "CPATH": '"$PIXI_PROJECT_ROOT/.local/xqilla/include:$CPATH"',
    "LIBRARY_PATH": '"$PIXI_PROJECT_ROOT/.local/xqilla/lib:$PIXI_PROJECT_ROOT/.pixi/envs/default/lib:$LIBRARY_PATH"',
}

TASKS = {
    "xqilla": '"$PIXI_PROJECT_ROOT/.local/xqilla/bin/xqilla"',
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None)
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else project_root()
    manifest = manifest_path(root)

    text = manifest.read_text()

    text = ensure_section(text, "activation.env")
    for key, value in ACTIVATION_ENV.items():
        text = upsert_key(text, "activation.env", key, value)

    text = ensure_section(text, "tasks")
    for key, value in TASKS.items():
        text = upsert_key(text, "tasks", key, value)

    manifest.write_text(text)
    print(f"Registered XQilla in {manifest}")


if __name__ == "__main__":
    main()
