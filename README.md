# Teltonika RUT956 Data API

Read-only Python HTTP API for GNSS, RS232, and RS485 data from a router at
`192.168.1.1`. Requires Python 3.11 or newer.

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

## Run

PowerShell, from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Open API documentation at <http://127.0.0.1:8000/docs>.

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
There is no durable storage, delivery acknowledgement, or write endpoint.
Serial connections retry automatically after failures.

## Print a Stream

With the API running, execute the interactive script in Git Bash, WSL, or a
Linux/macOS shell:

```sh
sh print_data.sh
```

Choose **GNSS**, **rs232**, or **rs485** (or **1**, **2**, **3**). The script
prints retained events first, then polls once per second and prints new events.
GNSS output is raw NMEA lines; serial output shows timestamps, escaped text,
and lossless hex. Stop with **Ctrl+C**. It retries if the API is unavailable.
Python 3 is required; the script selects the project's virtual environment when
available. Windows PowerShell cannot execute shell scripts directly; use Git
Bash or WSL.

To select a different API address:

```sh
API_URL=http://127.0.0.1:8000 sh print_data.sh
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
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests simulate TCP endpoints on localhost. No router, enabled GNSS service,
serial device, or credentials are required.

## References

- [RUT956 GPS](https://wiki.teltonika-networks.com/view/RUT956_GPS)
- [RUT956 Serial Utilities](https://wiki.teltonika-networks.com/view/RUT956_Serial_Utilities)
