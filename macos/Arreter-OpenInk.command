#!/bin/bash
set -euo pipefail
OPENINK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
if [ -x "$OPENINK_ROOT/.venv-macos/bin/python" ]; then
    exec "$OPENINK_ROOT/.venv-macos/bin/python" "$OPENINK_ROOT/macos/openink_macos.py" --stop-agent
fi
if [ -x "$HOME/Applications/OpenInk.app/Contents/MacOS/OpenInk" ]; then
    exec "$HOME/Applications/OpenInk.app/Contents/MacOS/OpenInk" --stop-agent
fi
printf '%s\n' 'Aucune installation OpenInk de ce kit n’a été trouvée.'
