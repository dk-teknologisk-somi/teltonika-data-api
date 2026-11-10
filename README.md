# Teltonika RUT956 Data API

Python HTTP API for GNSS, RS232, and RS485 data from a router at
`192.168.1.1`. GNSS is read-only; RS232 and RS485 also support sending bytes
to the attached device for polled (request/response) instruments. Requires
Python 3.11 or newer.

## Protocol Choice

Use **NMEA forwarding over TCP for GNSS**, and **raw Serial over IP over TCP**
for RS232 and RS485. The Python service exposes the received data over HTTP.

The GPS page's HTTP/HTTPS option pushes data to a remote server; it is not an
endpoint you can poll at `http://192.168.1.1`. NMEA is a straightforward choice
for a live local feed with standard sentence parsing. For remote deployments,
use a VPN or a TLS-protected transport; this collector uses unencrypted TCP.

| Data | Initiator | Destination | Format |
| --- | --- | --- | --- |
| GNSS | Router | Computer's LAN IP, TCP 8500 | Checksummed NMEA, CRLF-delimited |
| RS232 | Python collector | 192.168.1.1, TCP 5001 | Raw serial bytes |
| RS485 | Python collector | 192.168.1.1, TCP 5002 | Raw serial bytes |

Serial ports 5001/5002 are example configuration choices, not router defaults.
No router login is needed for these configured TCP services. This program does
not change router configuration or use the RutOS management API.

## Router Configuration

1. Open the router WebUI at `http://192.168.1.1`.
2. Under **Services > GPS > General**, enable GPS. Connect the GNSS antenna and
	place it where it has a clear view of the sky.
3. Under **GPS > NMEA > NMEA forwarding**, enable forwarding, set the host to
	**the computer running Python's LAN IP**, protocol **TCP**, port **8500**,
	prefix **none**, and enable **Contain connection**. Do not enter the router's
	own address or `127.0.0.1` as the forwarding destination.
4. In NMEA sentence settings, enable forwarding for **GGA** and **RMC** at a
	suitable interval, for example once per second. Select the corresponding
	supported talker variants, such as GPGGA/GNGGA and GPRMC/GNRMC.
5. Under **Services > Serial Utilities > Over IP**, create separate instances
	for **RS232** and **RS485**. Use **Server** mode, **TCP**, listening ports
	**5001** and **5002**, **Raw mode on**, **Remove all zeros off**, and TCP/serial
	echo off. Keep connections open. Match baud rate, parity, stop bits, flow
	control, and RS485 duplex mode to the attached devices.
6. Do not enable GPS **NMEA serial forwarding** onto serial interfaces used for
	external devices. Avoid competing services using the same serial interface.
7. Allow inbound TCP 8500 through the computer's firewall from `192.168.1.1`
	only. Restrict the router's serial TCP ports to the collector computer.

Menu labels can vary by firmware. No hardware configuration has been performed
by this project.

## Project Layout

| Path | Contents |
| --- | --- |
| `src/main.py` | The API service |
| `tests/` | Unit tests |
| `scripts/` | Start, stream-printing, and build scripts |
| `requirements/` | `runtime.txt`, `dev.txt` (tests), `build.txt` (PyInstaller) |
| `packaging/` | PyInstaller spec for the standalone executable |

## Run

PowerShell, from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements\runtime.txt
.\.venv\Scripts\python.exe src\main.py
```

On Linux (or Git Bash), `sh scripts/start_api.sh` creates `.venv`, installs
dependencies if needed, and starts the API.

Open API documentation at <http://127.0.0.1:8000/docs>.

## Standalone Executable

For tablets and other machines without Python, use the single-file executable.
It bundles Python and all dependencies; no installation is required.

1. Download the file for the tablet from the GitHub release (or the
	**Build executables** workflow run's artifacts):
	`teltonika-data-api-windows-x64.exe` (also runs on Windows on ARM via
	emulation), `teltonika-data-api-linux-x64`, or
	`teltonika-data-api-linux-arm64`.
2. Windows: double-click the `.exe`. SmartScreen may warn about an unsigned
	app (**More info > Run anyway**), and Windows Firewall asks to allow
	network access the first time; allow it on private networks so the router
	can forward GNSS to TCP 8500.
3. Linux: `chmod +x teltonika-data-api-linux-x64` and run it. The Linux builds
	need glibc 2.35 or newer (Ubuntu 22.04, Debian 12, or later).

A console window shows the log; close it or press **Ctrl+C** to stop. The
environment settings below work the same way for the executable.

Pushing a tag such as `v1.0.0` builds all executables on GitHub Actions and
attaches them to a release; the workflow can also be started manually.

To build locally, run the script for the OS you are on. PyInstaller does not
cross-compile, so build the Windows `.exe` on Windows and the Linux binary on
Linux (on the same CPU architecture as the tablet). Both scripts need Python
3.11+, create `.venv` if missing, and install `requirements/build.txt`.

| OS | Command | Result |
| --- | --- | --- |
| Linux | `sh scripts/build_linux.sh` | `dist/teltonika-data-api` |
| Windows | Double-click `scripts\build_windows.bat` | `dist\teltonika-data-api.exe` |

Optional environment settings, applied before starting:

```powershell
$env:ROUTER_HOST = "192.168.1.1"
$env:GNSS_BIND = "0.0.0.0"
$env:GNSS_PORT = "8500"
$env:RS232_PORT = "5001"
$env:RS485_PORT = "5002"
```

Set either serial port to `0` to disable its connection while configuring the
router. `ROUTER_HOST` must be the router's literal IPv4 address: incoming GNSS
connections are accepted only from that address. The GNSS listener binds all
interfaces by default so the router can reach it; the HTTP API binds localhost.
Use one service process only, since it owns the GNSS listening port.

## Endpoints

| GET endpoint | Result |
| --- | --- |
| `/health` | Process liveness and per-source connection/error/freshness status |
| `/api/gnss` | Latest sentence and latest GGA/RMC/GNS position |
| `/api/gnss/events?limit=100` | Recent valid NMEA sentences and parsed fields |
| `/api/rs232/events?limit=100` | Recent RS232 byte chunks |
| `/api/rs485/events?limit=100` | Recent RS485 byte chunks |

| POST endpoint | Result |
| --- | --- |
| `/api/rs232/send` | Send bytes out the RS232 port |
| `/api/rs485/send` | Send bytes out the RS485 port |

The send body is JSON with exactly one of `text` (UTF-8 encoded before
sending) or `base64` (lossless, for binary or exact control characters),
limited to 4096 decoded bytes. Line endings are not added automatically;
include `\r\n` or whatever the device expects. Responses from the device
appear in `/api/<source>/events` as usual. Sending returns `503` when the
serial TCP connection to the router is down.

```sh
curl -X POST http://127.0.0.1:8000/api/rs232/send \
	-H 'Content-Type: application/json' -d '{"text": "MEAS?\r\n"}'
```

Anyone who can reach the HTTP API can transmit arbitrary bytes to the serial
devices. Keep the API bound to localhost, or restrict access before exposing
it.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/gnss
Invoke-RestMethod http://127.0.0.1:8000/api/rs485/events
```

No GNSS yet is normal until forwarding is enabled: position is `null`, and
status reports disconnected/stale. No-fix sentences clear coordinates instead
of presenting an old fix as current. A position has its own `stale` flag after
15 seconds without a position sentence; timestamps are server reception times
in UTC, not the GNSS measurement time. Cached router sentences may be older.
`/health` reports process liveness, not proof that hardware data is available.

Serial results include lossless `base64` and `hex`, plus best-effort UTF-8
`text`. TCP chunks are **not device messages**: a message can span chunks, or
one chunk can contain several messages. Each source retains at most 1,000
events in RAM, oldest first; data is lost on restart or overwritten at capacity.
There is no durable storage or delivery acknowledgement. Serial connections
retry automatically after failures.

## Print a Stream

With the API running, execute the interactive script in Git Bash, WSL, or a
Linux/macOS shell:

```sh
sh scripts/print_data.sh
```

Choose **GNSS**, **rs232**, or **rs485** (or **1**, **2**, **3**). The script
prints retained events first, then polls once per second and prints new events.
GNSS output is raw NMEA lines; serial output shows timestamps, escaped text,
and lossless hex. Stop with **Ctrl+C**. It retries if the API is unavailable,
and reports the source's router connection status (on stderr) whenever it
changes, so a silent stream shows why no data is arriving.
Python 3 is required; the script selects the project's virtual environment when
available. Windows PowerShell cannot execute shell scripts directly; use Git
Bash or WSL.

To select a different API address:

```sh
API_URL=http://127.0.0.1:8000 sh scripts/print_data.sh
```

This is a best-effort live display, not a durable stream: events can be missed
if more than 1,000 arrive between polls. Reception timestamps suppress repeats.

**RS485 is an electrical interface, not a data protocol.** This collector reads
devices that stream data. Modbus RTU slaves and other request/response devices
will remain silent until polled. Supporting them needs the device protocol,
slave IDs, register map, and serial settings. Do not assume Modbus TCP is the
same as transparent TCP carrying Modbus RTU.

The HTTP API has no authentication. Keep it on localhost, or put it behind an
authenticated TLS reverse proxy before exposing it beyond a trusted machine.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements\dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests simulate TCP endpoints on localhost. No router, enabled GNSS service,
serial device, or credentials are required.

## References

- [RUT956 GPS](https://wiki.teltonika-networks.com/view/RUT956_GPS)
- [RUT956 Serial Utilities](https://wiki.teltonika-networks.com/view/RUT956_Serial_Utilities)
