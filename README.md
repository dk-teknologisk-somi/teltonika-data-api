# Teltonika RUT956 Data API

A small HTTP API that collects **GNSS**, **RS232** and **RS485** data from a
Teltonika RUT956 router (`192.168.1.1`) and serves it as JSON on
<http://127.0.0.1:8000>.

Interactive API docs: <http://127.0.0.1:8000/docs>


## Run

| How | Command |
| --- | --- |
| Executable (no Python needed) | Windows: double-click `teltonika-data-api.exe` · Linux: `./teltonika-data-api` |
| From source (Python 3.11+) | `sh scripts/start_api.sh` |

Stop with **Ctrl+C**. The computer must be on the router's LAN (`192.168.1.x`).

## Endpoints

| Method | Endpoint | Returns |
| --- | --- | --- |
| GET | `/health` | Connection status for all sources |
| GET | `/api/gnss` | Latest position and latest NMEA sentence |
| GET | `/api/gnss/events?limit=100` | Recent NMEA sentences, oldest first |
| GET | `/api/rs232/events?limit=100` | Recent RS232 data, oldest first |
| GET | `/api/rs485/events?limit=100` | Recent RS485 data, oldest first |
| POST | `/api/rs232/send` | Sends bytes to the RS232 device |
| POST | `/api/rs485/send` | Sends bytes to the RS485 device |

`limit` is 1–1000 (default 100). The API keeps the latest 1000 events per
source in memory; they are lost on restart. All timestamps are UTC, when the 
API received the data.

Readable output: `curl -s 127.0.0.1:8000/health | python3 -m json.tool`

### Status object

Every response includes a status for its source:

```json
{
  "enabled": true,
  "connected": true,
  "last_received_at": "2026-11-10T09:10:12.035449+00:00",
  "error": null,
  "received_count": 6772,
  "invalid_count": 13,
  "age_seconds": 0.81,
  "stale": false
}
```

| Field | Meaning |
| --- | --- |
| `enabled` | Source is turned on (serial port not set to `0`) |
| `connected` | Router connection is open |
| `last_received_at` | When data last arrived, or `null` |
| `error` | Latest connection/parse error, or `null` |
| `received_count` / `invalid_count` | Events received / invalid NMEA lines |
| `age_seconds` | Seconds since last data |
| `stale` | No data for more than 15 seconds |

### `GET /health`

```json
{
  "status": "running",
  "router": "192.168.1.1",
  "sources": { "gnss": { ...status }, "rs232": { ...status }, "rs485": { ...status } }
}
```

### `GET /api/gnss`

```json
{
  "status": { ...status },
  "position": {
    "valid": true,
    "latitude": 56.200426,
    "longitude": 10.157915,
    "sentence_type": "RMC",
    "received_at": "2026-11-10T09:10:12.035449+00:00",
    "stale": false
  },
  "latest": { ...GNSS event }
}
```

`position` is `null` until a GGA/RMC/GNS sentence arrives. Without a fix,
`valid` is `false` and the coordinates are `null`.

### `GET /api/gnss/events`

```json
{
  "source": "gnss",
  "status": { ...status },
  "events": [
    {
      "raw": "$GPRMC,091012.00,A,5612.025573,N,01009.474914,E,0.0,104.0,101126,0.2,W,A,V*51",
      "sentence_type": "RMC",
      "talker": "GP",
      "fields": { "timestamp": "09:10:12+00:00", "status": "A", "lat": "5612.025573", "...": "..." },
      "received_at": "2026-11-10T09:10:12.035449+00:00"
    }
  ]
}
```

### `GET /api/rs232/events` and `/api/rs485/events`

```json
{
  "source": "rs232",
  "status": { ...status },
  "events": [
    {
      "size": 7,
      "base64": "MjMuNEMNCg==",
      "hex": "32332e34430d0a",
      "text": "23.4C\r\n",
      "received_at": "2026-11-10T09:10:12.035449+00:00"
    }
  ]
}
```

Each event is a chunk of bytes as received over TCP, not necessarily one
complete device message. `text` is best-effort UTF-8; `hex`/`base64` are exact.

### `POST /api/rs232/send` and `/api/rs485/send`

Body: exactly one of `text` or `base64` (max 4096 bytes). No line ending is
added — include `\r\n` if the device needs it.

```sh
curl -X POST 127.0.0.1:8000/api/rs232/send \
  -H 'Content-Type: application/json' -d '{"text": "MEAS?\r\n"}'
```

```json
{ "source": "rs232", "sent_bytes": 7, "sent_at": "2026-11-10T09:10:12.512301+00:00" }
```

The device's reply shows up in `/api/rs232/events`. Errors: `422` for an
invalid body, `503` if the serial port is not connected.

## Router Setup

| Data | Router setting | Value |
| --- | --- | --- |
| GNSS | Services > GPS > NMEA forwarding | Host: this computer's IP, TCP, port `8500`. Enable GGA and RMC. |
| RS232 | Services > Serial Utilities > Over IP | Server, TCP, port `5001`, raw mode |
| RS485 | Services > Serial Utilities > Over IP | Server, TCP, port `5002`, raw mode |

Allow inbound TCP `8500` from `192.168.1.1` in the computer's firewall.

## Settings

Optional environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ROUTER_HOST` | `192.168.1.1` | Router IP (GNSS is only accepted from this address) |
| `GNSS_PORT` | `8500` | Port the API listens on for NMEA |
| `RS232_PORT` | `5001` | Router RS232 port (`0` disables) |
| `RS485_PORT` | `5002` | Router RS485 port (`0` disables) |

The API has no authentication and only listens on `127.0.0.1`.

## Print a Live Stream

```sh
sh scripts/print_data.sh
```

Choose GNSS, rs232 or rs485. Prints new data as it arrives, plus connection
status changes.

## Build the Executable

PyInstaller bundles Python and all dependencies into one file. Build on the
OS you are targeting:

| OS | Command | Result |
| --- | --- | --- |
| Linux | `sh scripts/build_linux.sh` | `dist/teltonika-data-api` |
| Windows | Double-click `scripts\build_windows.bat` | `dist\teltonika-data-api.exe` |

Pushing a `v*` tag builds Windows and Linux (x64/arm64) executables on GitHub
Actions and attaches them to a release.

## Tests

```sh
.venv/bin/python -m pip install -r requirements/dev.txt
.venv/bin/python -m unittest discover -s tests
```
