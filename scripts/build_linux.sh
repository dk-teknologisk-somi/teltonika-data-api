#!/bin/sh
# Builds dist/teltonika-data-api for the Linux machine/architecture this runs on.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

if [ ! -x .venv/bin/python ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Python 3.11 or newer is required. Install python3 and python3-venv first.\n' >&2
        exit 1
    fi
    printf 'Creating virtual environment in %s/.venv...\n' "$project_dir" >&2
    python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements/build.txt
.venv/bin/python -m PyInstaller packaging/teltonika-data-api.spec --noconfirm --clean

printf '\nBuilt: %s/dist/teltonika-data-api\n' "$project_dir" >&2
