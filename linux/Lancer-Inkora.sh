#!/bin/sh
set -eu
INKORA_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$INKORA_DIR/inkora_linux.py" "$@"
