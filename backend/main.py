import time
import asyncio
import json
from contextlib import asynccontextmanager
from utils import parse_market_data_packet
from telemetry_accumulator import Accumulator
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

UDP_HOST = "0.0.0.0"
UDP_PORT = 9999
TELEMETRY_HOST = "0.0.0.0"
TELEMETRY_PORT = 8125
FLUSH_INTERVAL_SEC = 0.05
ACC_WIND_SIZE = 5

market_data = {"bids": [], "asks": [], "sequence": 0, "timestamp": 0}
market_clients: set[WebSocket] = set()
udp_message_buffer: list[dict | str] = []

udp_bot_telemetry_buffer: list[dict] = []
bot_telemetry_clients: set[WebSocket] = set()

benchmark_system_health = {
    "event_loop_lag_ms": 0.0,
    "accumulator_compute_ms": 0.0,
    "bot_emission_rate": 0.0
}

_bot_emission_accumulator = 0

accumulator = Accumulator(window_size=ACC_WIND_SIZE)

class TelemetryUDPProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, add: tuple[str, int]):
        global _bot_emission_accumulator
        try:
            text = data.decode("utf-8")
            metrics = text.splitlines()
            engine_metrics = []
            for m in metrics:
                if not m.strip():
                    continue # Skiping empty lines
                    
                # Intercept the system health metric
                if m.startswith("benchmark.bot.emission"):
                    val = float(m.split(':')[1].split('|')[0])
                    _bot_emission_accumulator += val
                else:
                    engine_metrics.append(m)

            if engine_metrics:
                for i in range(0, len(engine_metrics), 3):
                    chunk = engine_metrics[i:i+3]
                    # Only accumulate if we have a full set of 3
                    if len(chunk) == 3:
                        accumulator.accumulate(chunk)

        except (UnicodeDecodeError, ValueError):
            print(f"Invalid telemetry packet from {add}")

async def monitor_event_loop_lag():
    """Measures FastAPI's internal async event loop lag."""
    expected_sleep = 0.1
    while True:
        start_time = time.perf_counter()
        await asyncio.sleep(expected_sleep)
        actual_sleep = time.perf_counter() - start_time
        
        lag_ms = max(0.0, (actual_sleep - expected_sleep) * 1000)
        benchmark_system_health["event_loop_lag_ms"] = lag_ms

async def aggregate_bot_emission():
    global _bot_emission_accumulator
    while True:
        await asyncio.sleep(1.0)
        benchmark_system_health["bot_emission_rate"] = _bot_emission_accumulator
        _bot_emission_accumulator = 0

class ExchangeUDPProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        # print(f"Received {len(data)} bytes from Matching Engine")
        parsed_msg = parse_market_data_packet(data)
        if parsed_msg:
            if parsed_msg["type"] == "BOOK_SNAPSHOT":
                market_data["bids"] = parsed_msg["bids"]
                market_data["asks"] = parsed_msg["asks"]
                market_data["sequence"] = parsed_msg["sequence"]
                market_data["timestamp"] = parsed_msg["timestamp"]
            udp_message_buffer.append(parsed_msg)
                
async def broadcast_bot_telemetry():
    while True:
        await asyncio.sleep(0.002)
        t_start = time.perf_counter()
        metrics = accumulator.get_metrics()
        compute_ms = (time.perf_counter() - t_start) * 1000
        benchmark_system_health["accumulator_compute_ms"] = compute_ms

        payload = json.dumps({
            "type": "BOT_TELE_BATCH",
            "timestamp": time.time(),
            "metrics": metrics,
            "system_health": benchmark_system_health
        })

        disconnected_clients = set()
        for client in list(bot_telemetry_clients):
            try:
                await client.send_text(payload)
            except Exception:
                disconnected_clients.add(client)
        
        bot_telemetry_clients.difference_update(disconnected_clients)

async def broadcast_market_data():
    global udp_message_buffer
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SEC)

        if not udp_message_buffer or not market_clients:
            continue

        current_batch = udp_message_buffer
        udp_message_buffer = []

        payload = json.dumps({
            "type": "MARKET_DATA_BATCH",
            "timestamp": time.time(),
            "snapshot" : market_data,
            "updates": current_batch,
        })

        disconnected_clients = set()
        for client in list(market_clients):
            try:
                await client.send_text(payload)
            except Exception:
                disconnected_clients.add(client)

        market_clients.difference_update(disconnected_clients)

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: ExchangeUDPProtocol(), local_addr=(UDP_HOST, UDP_PORT)
    )
    print(f"UDP Server listening on {UDP_HOST}:{UDP_PORT}")

    telemetry_transport, telemetry_protocol = await loop.create_datagram_endpoint(
        lambda: TelemetryUDPProtocol(), local_addr=(TELEMETRY_HOST, TELEMETRY_PORT)
    )

    broadcast_task = asyncio.create_task(broadcast_market_data())
    broadcast_tele_bot = asyncio.create_task(broadcast_bot_telemetry())
    loop_monitor = asyncio.create_task(monitor_event_loop_lag())
    emission_monitor = asyncio.create_task(aggregate_bot_emission())

    try:
        yield
    finally:
        broadcast_task.cancel()
        broadcast_tele_bot.cancel()
        loop_monitor.cancel()
        emission_monitor.cancel()
        await asyncio.gather(
            broadcast_task,
            broadcast_tele_bot,
            return_exceptions=True
        )
        transport.close()
        telemetry_transport.close()
        print("LIFESPAN 11 - shutdown complete")

app = FastAPI(lifespan=lifespan)

@app.websocket("/ws/market")
async def websocket_market_endpoint(websocket: WebSocket):
    await websocket.accept()
    market_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        market_clients.discard(websocket)

@app.websocket("/ws/telemetry")
async def websocket_bot_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    bot_telemetry_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        bot_telemetry_clients.discard(websocket)

@app.get("/leaderboard")
async def get_leaderboard():
    """Fullfill leaderboard request"""
    pass

@app.get("/performance")
async def get_performance():
    """Fullfill usercode performance request"""
    pass

def start_server():
    uvicorn.run(
        app,
        host = "0.0.0.0",
        port = 8000,
        reload = False
    )

if __name__ == "__main__":
    start_server()