#!/bin/bash
# Sourced by the public .command launchers. Paths with spaces stay quoted.
set -euo pipefail
OPENINK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

openink_prepare() {
    if [ "$(uname -s)" != "Darwin" ]; then
        printf '%s\n' 'Ce kit doit être lancé sur un Mac.' >&2
        return 1
    fi
    local candidate
    OPENINK_PYTHON=""
    for candidate in "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14" "/opt/homebrew/bin/python3.14" "/usr/local/bin/python3.14"; do
        if [ -x "$candidate" ]; then
            OPENINK_PYTHON="$candidate"
            break
        fi
    done
    if [ -z "$OPENINK_PYTHON" ]; then
        OPENINK_PYTHON="$(command -v python3.14 || true)"
    fi
    if [ -z "$OPENINK_PYTHON" ]; then
        printf '%s\n' 'Installe Python 3.14 pour macOS depuis python.org, puis relance ce fichier.'
        /usr/bin/open 'https://www.python.org/downloads/release/python-31410/'
        return 1
    fi
    "$OPENINK_PYTHON" -c 'import sys,tkinter; assert sys.version_info[:2] == (3,14); root=tkinter.Tk(); root.withdraw(); root.destroy()'
    if [ ! -x "$OPENINK_ROOT/.venv-macos/bin/python" ]; then
        "$OPENINK_PYTHON" -m venv "$OPENINK_ROOT/.venv-macos"
    fi
    OPENINK_PYTHON="$OPENINK_ROOT/.venv-macos/bin/python"
    local architecture
    architecture="$("$OPENINK_PYTHON" -c 'import platform; print(platform.machine())')"
    if [ -f "$OPENINK_ROOT/macos/wheels/$architecture/requirements-lock.txt" ]; then
        "$OPENINK_PYTHON" -m pip install --disable-pip-version-check --only-binary=:all: --no-index \
            --find-links "$OPENINK_ROOT/macos/wheels/$architecture" --require-hashes \
            -r "$OPENINK_ROOT/macos/wheels/$architecture/requirements-lock.txt"
    else
        "$OPENINK_PYTHON" -m pip install --disable-pip-version-check --only-binary=:all: -r "$OPENINK_ROOT/macos/requirements.txt"
    fi
    cd -- "$OPENINK_ROOT"
}
