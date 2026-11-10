#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ -x "$project_dir/.venv/bin/python" ]; then
    python="$project_dir/.venv/bin/python"
elif [ -x "$project_dir/.venv/Scripts/python.exe" ]; then
    python="$project_dir/.venv/Scripts/python.exe"
else
    printf 'Creating virtual environment in %s/.venv...\n' "$project_dir" >&2
    if command -v python3 >/dev/null 2>&1; then
        base_python=python3
    elif command -v python >/dev/null 2>&1; then
        base_python=python
    else
        printf 'Python 3 is required. Install Python first.\n' >&2
        exit 1
    fi
    "$base_python" -m venv "$project_dir/.venv"
    if [ -x "$project_dir/.venv/bin/python" ]; then
        python="$project_dir/.venv/bin/python"
    else
        python="$project_dir/.venv/Scripts/python.exe"
    fi
fi

if ! "$python" -c 'import fastapi, uvicorn, pynmea2' >/dev/null 2>&1; then
    printf 'Installing dependencies from requirements/runtime.txt...\n' >&2
    "$python" -m pip install -r "$project_dir/requirements/runtime.txt"
fi

printf 'Starting API server. Press Ctrl+C to stop.\n' >&2
exec "$python" "$project_dir/src/main.py"
