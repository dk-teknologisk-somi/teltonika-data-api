#!/bin/sh
set -eu

printf 'What should be streamed?\n  1) GNSS\n  2) rs232\n  3) rs485\nChoice: ' >&2
read -r choice || exit 0
case "$choice" in
    1|GNSS|gnss) source=gnss ;;
    2|RS232|rs232) source=rs232 ;;
    3|RS485|rs485) source=rs485 ;;
    *) printf 'Invalid choice. Use GNSS, rs232, rs485, or 1-3.\n' >&2; exit 1 ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$script_dir/.venv/bin/python" ]; then
    python="$script_dir/.venv/bin/python"
elif [ -x "$script_dir/.venv/Scripts/python.exe" ]; then
    python="$script_dir/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    python=python3
elif command -v python >/dev/null 2>&1; then
    python=python
else
    printf 'Python 3 is required. Install Python or create the project .venv.\n' >&2
    exit 1
fi

exec "$python" -u - "$source" "${API_URL:-http://127.0.0.1:8000}" <<'PYTHON'
import json
import sys
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import urlopen


def stream(source, api_url):
    url = f"{api_url.rstrip('/')}/api/{source}/events?limit=1000"
    watermark = None
    previous_error = None
    print(f"Streaming {source} from {api_url}. Press Ctrl+C to stop.", file=sys.stderr)
    try:
        while True:
            try:
                with urlopen(url, timeout=5) as response:
                    payload = json.load(response)
                events = payload["events"]
                next_watermark = watermark
                for event in events:
                    timestamp = datetime.fromisoformat(event["received_at"])
                    if watermark is not None and timestamp <= watermark:
                        continue
                    if source == "gnss":
                        print(event["raw"], flush=True)
                    else:
                        print(
                            f"{event['received_at']} text={event['text']!r} hex={event['hex']}",
                            flush=True,
                        )
                    if next_watermark is None or timestamp > next_watermark:
                        next_watermark = timestamp
                watermark = next_watermark
                if previous_error is not None:
                    print("API connection restored.", file=sys.stderr)
                previous_error = None
            except (URLError, OSError, ValueError, KeyError, TypeError) as exc:
                error = str(exc)
                if error != previous_error:
                    print(f"Cannot read API: {error}. Retrying...", file=sys.stderr)
                previous_error = error
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)


if __name__ == "__main__":
    stream(sys.argv[1], sys.argv[2])
PYTHON