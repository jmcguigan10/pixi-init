#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"

exec "$PYTHON" "$ROOT/.install/python/pixi_add_from_yml.py" \
    "$ROOT/.install/cfgs/add-basic.yml" \
    "$@"
