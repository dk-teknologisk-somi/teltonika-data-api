#!/bin/sh
# Exercises an RS PRO RS-3005P / RS-6005P (Korad protocol) power supply on RS232
# through the running API: sets a current limit, steps through voltages, and
# reads back the setpoints, actual output, and status.
#
# Usage: sh scripts/test_psu.sh [VOLTAGE ...]     (default: 1 3.3 5 9 12)
#        API_URL=http://127.0.0.1:8000 CURRENT_LIMIT=0.1 SOURCE=rs232 sh scripts/test_psu.sh
#
# Router RS232 Over IP settings for the PSU: 9600 baud, 8 data bits, no parity,
# 1 stop bit, flow control none.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -x "$project_dir/.venv/bin/python" ]; then
    python="$project_dir/.venv/bin/python"
elif [ -x "$project_dir/.venv/Scripts/python.exe" ]; then
    python="$project_dir/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    python=python3
elif command -v python >/dev/null 2>&1; then
    python=python
else
    printf 'Python 3 is required. Install Python or create the project .venv.\n' >&2
    exit 1
fi

exec "$python" -u - "${API_URL:-http://127.0.0.1:8000}" "${SOURCE:-rs232}" \
    "${CURRENT_LIMIT:-0.1}" "$@" <<'PYTHON'
import base64
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COMMAND_GAP = 0.1      # the PSU separates commands by silence (no terminator)
REPLY_TIMEOUT = 1.5
REPLY_QUIET = 0.2      # reply is complete after this long without new bytes
SETTLE_SECONDS = 1.0


class Psu:
    def __init__(self, api_url, source):
        self.base = f"{api_url.rstrip('/')}/api/{source}"
        self.source = source

    def _events(self):
        with urlopen(f"{self.base}/events?limit=1000", timeout=5) as response:
            return json.load(response)

    def send(self, command):
        body = json.dumps({"text": command}).encode()
        request = Request(f"{self.base}/send", data=body, method="POST",
                          headers={"Content-Type": "application/json"})
        try:
            urlopen(request, timeout=5).close()
        except HTTPError as exc:
            detail = json.load(exc).get("detail", exc.reason)
            raise SystemExit(f"Send failed ({exc.code}): {detail}") from None
        time.sleep(COMMAND_GAP)

    def query(self, command):
        before = self._events()["status"]["received_count"]
        self.send(command)
        data = b""
        deadline = time.monotonic() + REPLY_TIMEOUT
        last_change = None
        while time.monotonic() < deadline:
            payload = self._events()
            new = payload["status"]["received_count"] - before
            chunks = payload["events"][-new:] if new > 0 else []
            received = b"".join(base64.b64decode(event["base64"]) for event in chunks)
            if received != data:
                data, last_change = received, time.monotonic()
            elif data and time.monotonic() - last_change >= REPLY_QUIET:
                break
            time.sleep(0.05)
        return data

    def query_text(self, command):
        return self.query(command).decode("ascii", errors="replace").strip()

    def query_float(self, command):
        reply = self.query_text(command)
        try:
            return float(reply)
        except ValueError:
            return None


def describe_status(raw):
    if len(raw) != 1:
        return f"? ({raw.hex() or 'no reply'})"
    bits = raw[0]
    mode = "CV" if bits & 0x01 else "CC"
    output = "ON" if bits & 0x40 else "OFF"
    return f"{mode}, output {output}"


def fmt(value, unit):
    if value is None:
        return "     n/a"
    return f"{value:6.2f} {unit}" if unit == "V" else f"{value:6.3f} {unit}"


def main():
    api_url, source, current_limit = sys.argv[1], sys.argv[2], float(sys.argv[3])
    voltages = [float(v) for v in sys.argv[4:]] or [1.0, 3.3, 5.0, 9.0, 12.0]
    psu = Psu(api_url, source)

    try:
        status = psu._events()["status"]
    except (URLError, OSError) as exc:
        raise SystemExit(f"Cannot reach the API at {api_url}: {exc}")
    if not status["connected"]:
        raise SystemExit(f"{source} is not connected to the router: {status['error']}")

    identity = psu.query_text("*IDN?")
    print(f"Device: {identity or 'no reply. Check cable (try swapping pins 2 and 3) and router RS232 settings: 9600 8N1, flow control none'}")
    if not identity:
        sys.exit(1)

    print(f"Current limit: {current_limit:.3f} A")
    print(f"{'Set V':>8} | {'VSET?':>8} | {'VOUT':>8} | {'IOUT':>9} | Status")
    print("-" * 56)
    psu.send(f"ISET1:{current_limit:.3f}")
    psu.send("VSET1:0.00")
    psu.send("OUT1")
    try:
        for voltage in voltages:
            psu.send(f"VSET1:{voltage:.2f}")
            time.sleep(SETTLE_SECONDS)
            vset = psu.query_float("VSET1?")
            vout = psu.query_float("VOUT1?")
            iout = psu.query_float("IOUT1?")
            state = describe_status(psu.query("STATUS?"))
            print(f"{voltage:6.2f} V | {fmt(vset, 'V')} | {fmt(vout, 'V')} | {fmt(iout, 'A')} | {state}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        psu.send("OUT0")
        psu.send("VSET1:0.00")
        print(f"Output off. Status: {describe_status(psu.query('STATUS?'))}")


if __name__ == "__main__":
    main()
PYTHON
