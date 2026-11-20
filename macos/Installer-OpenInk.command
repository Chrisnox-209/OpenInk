#!/bin/bash
set -euo pipefail
source "$(cd -- "$(dirname -- "$0")" && pwd)/bootstrap.sh"
openink_prepare
"$OPENINK_PYTHON" -m unittest discover -s "$OPENINK_ROOT/macos/tests" -v
"$OPENINK_PYTHON" "$OPENINK_ROOT/macos/build_macos.py"
"$OPENINK_PYTHON" "$OPENINK_ROOT/macos/install_app.py"
