from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Iterable, Mapping


def project_root() -> Path:
    env_root = os.environ.get("PIXI_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    here = Path(__file__).resolve()

    for candidate in [here, *here.parents]:
        if (candidate / "pixi.toml").exists():
            return candidate
        if (candidate / ".bin" / "pixi").exists():
            return candidate

    return Path.cwd().resolve()


def pixi_path(root: Path) -> Path:
    pixi = root / ".bin" / "pixi"
    if not pixi.exists():
        raise SystemExit(f"Missing pixi executable: {pixi}")
    if not os.access(pixi, os.X_OK):
        raise SystemExit(f"pixi exists but is not executable: {pixi}")
    return pixi


def manifest_path(root: Path) -> Path:
    manifest = root / "pixi.toml"
    if not manifest.exists():
        raise SystemExit(f"Missing pixi.toml: {manifest}")
    return manifest


def pixi_env_path(root: Path) -> Path:
    return root / ".pixi" / "envs" / "default"


def run(
    cmd: Iterable[str | Path],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    rendered = [str(part) for part in cmd]
    print("+", shlex.join(rendered))
    subprocess.run(rendered, cwd=str(cwd) if cwd else None, env=env, check=True)


def try_run(
    cmd: Iterable[str | Path],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    try:
        run(cmd, cwd=cwd, env=env)
        return True
    except subprocess.CalledProcessError:
        return False


def first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None