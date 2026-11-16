#!/bin/sh
set -eu
OPENINK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$OPENINK_DIR/openink_linux.py" "$@"
