import asyncio
import base64
import os
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import pynmea2
import uvicorn
from fastapi import FastAPI, Query


def now() -> datetime:
    return datetime.now(timezone.utc)


def port_from_env(name: str, default: int) -> int | None:
    value = int(os.getenv(name, str(default)))
    if not 0 <= value <= 65535:
        raise ValueError(f"{name} must be between 0 and 65535")
    return value or None


@dataclass(frozen=True)
class Settings:
    router_host: str = "192.168.1.1"
    gnss_bind: str = "0.0.0.0"
    gnss_port: int = 8500
    rs232_port: int | None = 5001
    rs485_port: int | None = 5002
    history_size: int = 1000
    retry_seconds: float = 3.0
    stale_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            router_host=os.getenv("ROUTER_HOST", "192.168.1.1"),
            gnss_bind=os.getenv("GNSS_BIND", "0.0.0.0"),
            gnss_port=port_from_env("GNSS_PORT", 8500) or 8500,
            rs232_port=port_from_env("RS232_PORT", 5001),
            rs485_port=port_from_env("RS485_PORT", 5002),
        )


class Collector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sources = {
            name: {
                "enabled": name == "gnss" or getattr(settings, f"{name}_port") is not None,
                "connected": False,
                "last_received_at": None,
                "error": None,
                "received_count": 0,
                "invalid_count": 0,
            }
            for name in ("gnss", "rs232", "rs485")
        }
        self.events = {
            name: deque(maxlen=settings.history_size) for name in self.sources
        }
        self.position: dict | None = None
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task] = set()
        self.gnss_connections = 0

    def record(self, source: str, event: dict) -> None:
        timestamp = now().isoformat()
        event["received_at"] = timestamp
        state = self.sources[source]
        state["last_received_at"] = timestamp
        state["received_count"] += 1
        state["error"] = None
        self.events[source].append(event)

    def ingest_nmea(self, raw: bytes) -> None:
        try:
            sentence = raw.decode("ascii").strip()
            if not sentence.startswith("$"):
                raise ValueError("NMEA sentence must start with $")
            message = pynmea2.parse(sentence, check=True)
            event = {
                "raw": sentence,
                "sentence_type": message.sentence_type,
                "talker": message.talker,
                "fields": {
                    field[1]: getattr(message, field[1]) for field in message.fields
                },
            }
            position = None
            if message.sentence_type in {"GGA", "RMC", "GNS"}:
                if message.sentence_type == "GGA":
                    valid = int(message.gps_qual or 0) > 0
                elif message.sentence_type == "RMC":
                    valid = message.status == "A"
                else:
                    valid = bool(message.mode_indicator.strip("N"))
                valid = valid and bool(message.lat and message.lon)
                position = {
                    "valid": valid,
                    "latitude": message.latitude if valid else None,
                    "longitude": message.longitude if valid else None,
                    "sentence_type": message.sentence_type,
                }
            self.record("gnss", event)
            if position is not None:
                position["received_at"] = event["received_at"]
                self.position = position
        except (ValueError, UnicodeError, AttributeError, pynmea2.ParseError) as exc:
            self.sources["gnss"]["invalid_count"] += 1
            self.sources["gnss"]["error"] = f"Invalid NMEA: {exc}"

    def ingest_serial(self, source: str, payload: bytes) -> None:
        self.record(source, {
            "size": len(payload),
            "base64": base64.b64encode(payload).decode("ascii"),
            "hex": payload.hex(),
            "text": payload.decode("utf-8", errors="replace"),
        })

    def status(self, source: str) -> dict:
        state = dict(self.sources[source])
        timestamp = state["last_received_at"]
        age = (now() - datetime.fromisoformat(timestamp)).total_seconds() if timestamp else None
        state["age_seconds"] = age
        state["stale"] = age is None or age > self.settings.stale_seconds
        return state

    async def gnss_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self.tasks.add(task)
        accepted = False
        try:
            peer = writer.get_extra_info("peername")
            if not peer or peer[0] != self.settings.router_host:
                return
            accepted = True
            self.gnss_connections += 1
            self.sources["gnss"]["connected"] = True
            while line := await reader.readline():
                self.ingest_nmea(line)
        except (OSError, ValueError) as exc:
            self.sources["gnss"]["error"] = str(exc)
        finally:
            if accepted:
                self.gnss_connections -= 1
                self.sources["gnss"]["connected"] = self.gnss_connections > 0
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            self.tasks.discard(task)

    async def serial_client(self, source: str, port: int) -> None:
        state = self.sources[source]
        while True:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.settings.router_host, port), timeout=5
                )
                state["connected"] = True
                state["error"] = None
                while payload := await reader.read(4096):
                    self.ingest_serial(source, payload)
                state["error"] = "Router closed connection; reconnecting"
            except (OSError, TimeoutError) as exc:
                state["error"] = str(exc)
            finally:
                state["connected"] = False
                if writer is not None:
                    writer.close()
                    with suppress(OSError):
                        await writer.wait_closed()
            await asyncio.sleep(self.settings.retry_seconds)

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self.gnss_client, self.settings.gnss_bind, self.settings.gnss_port, limit=4096
        )
        for source in ("rs232", "rs485"):
            port = getattr(self.settings, f"{source}_port")
            if port is not None:
                task = asyncio.create_task(self.serial_client(source, port))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.server is not None:
            await self.server.wait_closed()


def create_app(settings: Settings | None = None) -> FastAPI:
    collector = Collector(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await collector.start()
            yield
        finally:
            await collector.close()

    app = FastAPI(title="RUT956 Data API", lifespan=lifespan)
    app.state.collector = collector

    @app.get("/health")
    async def health():
        return {
            "status": "running",
            "router": collector.settings.router_host,
            "sources": {source: collector.status(source) for source in collector.sources},
        }

    @app.get("/api/gnss")
    async def gnss():
        position = dict(collector.position) if collector.position else None
        if position is not None:
            position["stale"] = (
                now() - datetime.fromisoformat(position["received_at"])
            ).total_seconds() > collector.settings.stale_seconds
        return {
            "status": collector.status("gnss"),
            "position": position,
            "latest": collector.events["gnss"][-1] if collector.events["gnss"] else None,
        }

    @app.get("/api/{source}/events")
    async def events(
        source: Literal["gnss", "rs232", "rs485"],
        limit: int = Query(default=100, ge=1, le=1000),
    ):
        return {
            "source": source,
            "status": collector.status(source),
            "events": list(collector.events[source])[-limit:],
        }

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)