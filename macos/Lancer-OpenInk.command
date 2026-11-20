#!/bin/bash
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/bootstrap.sh"
openink_prepare
exec "$OPENINK_PYTHON" "$OPENINK_ROOT/macos/openink_macos.py" "$@"
