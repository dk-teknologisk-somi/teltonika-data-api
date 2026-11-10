import asyncio
import base64
import sys
import unittest
from datetime import timedelta
from pathlib import Path

import httpx
import pynmea2
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import Collector, Settings, create_app, now


GGA = b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n"


def sentence(body: str) -> bytes:
    return f"${body}*{pynmea2.NMEASentence.checksum(body):02X}\r\n".encode()


class CollectorTests(unittest.TestCase):
    def test_position_and_checksum(self):
        collector = Collector(Settings())
        collector.ingest_nmea(GGA)
        self.assertAlmostEqual(collector.position["latitude"], 48.1173)
        self.assertAlmostEqual(collector.position["longitude"], 11.5166667)
        collector.ingest_nmea(GGA.replace(b"*47", b"*00"))
        self.assertEqual(collector.sources["gnss"]["invalid_count"], 1)
        self.assertEqual(collector.sources["gnss"]["received_count"], 1)

    def test_no_fix_clears_position(self):
        collector = Collector(Settings())
        collector.ingest_nmea(GGA)
        collector.ingest_nmea(sentence("GNRMC,123520,V,,,,,,,230394,,,N"))
        self.assertFalse(collector.position["valid"])
        self.assertIsNone(collector.position["latitude"])

    def test_binary_history_is_lossless_and_bounded(self):
        collector = Collector(Settings(history_size=2))
        for payload in (b"first", b"second", b"\x00\xff\x80\r\n"):
            collector.ingest_serial("rs485", payload)
        events = collector.events["rs485"]
        self.assertEqual(len(events), 2)
        self.assertEqual(base64.b64decode(events[-1]["base64"]), b"\x00\xff\x80\r\n")

    def test_api_and_stale_position(self):
        app = create_app(Settings(gnss_bind="127.0.0.1", gnss_port=0,
                                  rs232_port=None, rs485_port=None))
        collector = app.state.collector
        with TestClient(app) as client:
            self.assertIsNone(client.get("/api/gnss").json()["position"])
            collector.ingest_nmea(GGA)
            collector.position["received_at"] = (now() - timedelta(seconds=30)).isoformat()
            result = client.get("/api/gnss").json()
            self.assertTrue(result["position"]["stale"])
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/api/rs232/events").json()["events"], [])
            self.assertEqual(client.get("/api/unknown/events").status_code, 422)
            self.assertEqual(client.get("/api/gnss/events?limit=0").status_code, 422)

    def test_send_validation_and_unavailable(self):
        app = create_app(Settings(gnss_bind="127.0.0.1", gnss_port=0,
                                  rs232_port=None, rs485_port=None))
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/rs232/send", json={"text": "hi"}).status_code, 503)
            self.assertEqual(client.post("/api/rs232/send", json={}).status_code, 422)
            self.assertEqual(
                client.post("/api/rs232/send", json={"text": "a", "base64": "aGk="}).status_code,
                422,
            )
            self.assertEqual(client.post("/api/rs232/send", json={"base64": "!!!"}).status_code, 422)
            self.assertEqual(client.post("/api/rs232/send", json={"text": ""}).status_code, 422)
            self.assertEqual(client.post("/api/gnss/send", json={"text": "hi"}).status_code, 422)


class SocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_gnss_fragmented_tcp_and_shutdown(self):
        collector = Collector(Settings(router_host="127.0.0.1", gnss_bind="127.0.0.1",
                                       gnss_port=0, rs232_port=None, rs485_port=None))
        await collector.start()
        writer = None
        try:
            port = collector.server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(GGA[:20])
            await writer.drain()
            writer.write(GGA[20:] + GGA)
            await writer.drain()
            async def received():
                while collector.sources["gnss"]["received_count"] < 2:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(received(), 2)
            self.assertTrue(collector.position["valid"])
        finally:
            await asyncio.wait_for(collector.close(), 2)
            if writer:
                writer.close()
                await writer.wait_closed()

    async def test_serial_reconnect_and_binary_stream(self):
        connections = 0
        async def router(reader, writer):
            nonlocal connections
            connections += 1
            writer.write(b"\x00\xff")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(router, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        collector = Collector(Settings(router_host="127.0.0.1", retry_seconds=0.01))
        task = asyncio.create_task(collector.serial_client("rs232", port))
        try:
            async def received():
                while collector.sources["rs232"]["received_count"] < 2:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(received(), 2)
            self.assertGreaterEqual(connections, 2)
            self.assertEqual(collector.events["rs232"][-1]["hex"], "00ff")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            server.close()
            await server.wait_closed()

    async def test_send_roundtrip(self):
        received = asyncio.Queue()

        async def router(reader, writer):
            while data := await reader.read(4096):
                await received.put(data)
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(router, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        app = create_app(Settings(router_host="127.0.0.1", gnss_bind="127.0.0.1",
                                  gnss_port=0, rs232_port=port, rs485_port=None,
                                  retry_seconds=0.01))
        collector = app.state.collector
        await collector.start()
        try:
            async def connected():
                while "rs232" not in collector.writers:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(connected(), 2)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/rs232/send", json={"text": "MEAS?\r\n"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["sent_bytes"], 7)
                response = await client.post(
                    "/api/rs232/send",
                    json={"base64": base64.b64encode(b"\x00\xff").decode("ascii")},
                )
                self.assertEqual(response.status_code, 200)
                response = await client.post("/api/rs485/send", json={"text": "x"})
                self.assertEqual(response.status_code, 503)
            expected = b"MEAS?\r\n\x00\xff"
            data = b""
            while len(data) < len(expected):
                data += await asyncio.wait_for(received.get(), 2)
            self.assertEqual(data, expected)
        finally:
            await asyncio.wait_for(collector.close(), 2)
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()