#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$ROOT/.bin"
PIXI="$BIN_DIR/pixi"

mkdir -p \
    "$ROOT/.bin" \
    "$ROOT/.install/cfgs" \
    "$ROOT/.install/shell" \
    "$ROOT/.install/python" \
    "$ROOT/.install/src" \
    "$ROOT/.local"

detect_platform() {
    local os arch

    os="$(uname -s)"
    arch="$(uname -m)"

    case "$os:$arch" in
        Linux:x86_64)
            echo "linux-64"
            ;;
        Linux:aarch64|Linux:arm64)
            echo "linux-aarch64"
            ;;
        Darwin:x86_64)
            echo "osx-64"
            ;;
        Darwin:arm64)
            echo "osx-arm64"
            ;;
        *)
            echo "Unsupported platform: $os:$arch" >&2
            exit 1
            ;;
    esac
}

if [[ ! -x "$PIXI" ]]; then
    echo "Installing pixi into: $BIN_DIR"
    curl -fsSL https://pixi.sh/install.sh | PIXI_BIN_DIR="$BIN_DIR" PIXI_NO_PATH_UPDATE=1 sh
    chmod +x "$PIXI"
else
    echo "pixi already exists: $PIXI"
fi

if [[ ! -f "$ROOT/pixi.toml" ]]; then
    PROJECT_NAME="$(basename "$ROOT")"
    PLATFORM="$(detect_platform)"

    cat > "$ROOT/pixi.toml" <<EOF
[workspace]
channels = ["conda-forge"]
name = "$PROJECT_NAME"
platforms = ["$PLATFORM"]
version = "0.1.0"

[tasks]

[dependencies]
EOF
    echo "Created pixi.toml"
else
    echo "pixi.toml already exists"
fi

"$ROOT/.install/shell/add-basic.sh"
"$ROOT/.install/shell/build-xqilla.sh"
"$ROOT/.install/shell/verify-xqilla.sh"

echo
echo "Bootstrap complete."
echo "Try:"
echo "  $PIXI run xqilla -h"
