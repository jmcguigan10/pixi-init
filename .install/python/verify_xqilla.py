#!/usr/bin/env python3
from __future__ import annotations

import shlex
import subprocess
import sys

from common import manifest_path, pixi_path, project_root, run


def main() -> None:
    root = project_root()
    pixi = pixi_path(root)
    manifest = manifest_path(root)

    xqilla_bin = root / ".local" / "xqilla" / "bin" / "xqilla"

    if not xqilla_bin.exists():
        raise SystemExit(f"Missing XQilla binary: {xqilla_bin}")

    run([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        "xqilla",
        "-h",
    ])

    run([
        pixi,
        "run",
        "--manifest-path",
        manifest,
        "bash",
        "-lc",
        "which xqilla",
    ])

    if sys.platform.startswith("linux"):
        command = f"ldd {shlex.quote(str(xqilla_bin))}"
        result = subprocess.run(
            [
                str(pixi),
                "run",
                "--manifest-path",
                str(manifest),
                "bash",
                "-lc",
                command,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )

        print(result.stdout)

        if "not found" in result.stdout:
            raise SystemExit("Dynamic library check failed: ldd reported 'not found'.")

    print("XQilla verification passed.")


if __name__ == "__main__":
    main()