#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
pixi_project_root_resolved=""
if [[ -n "${PIXI_PROJECT_ROOT:-}" && -d "${PIXI_PROJECT_ROOT:-}" ]]; then
    pixi_project_root_resolved="$(cd "$PIXI_PROJECT_ROOT" && pwd)"
fi
python_path="$(command -v python || true)"

if [[ "$pixi_project_root_resolved" == "$ROOT" ]]; then
    case "$python_path" in
        "$ROOT"/.pixi/envs/*/bin/python)
            exec python "$ROOT/.install/python/verify_source_stack.py" "$@"
            ;;
    esac
fi

exec "$ROOT/.bin/pixi" run --manifest-path "$ROOT/pixi.toml" python \
    "$ROOT/.install/python/verify_source_stack.py" "$@"
