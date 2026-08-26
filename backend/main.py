import time
import asyncio
import json
from contextlib import asynccontextmanager
from utils import parse_binary_market_packet
from telemetry_accumulator import Accumulator
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

UDP_HOST = "0.0.0.0"
UDP_PORT = 9999
TELEMETRY_HOST = "0.0.0.0"
TELEMETRY_PORT = 8125
FLUSH_INTERVAL_SEC = 0.05
ACC_WIND_SIZE = 5

market_data = {"bids": [], "asks": []}
market_clients: set[WebSocket] = set()
udp_message_buffer: list[dict | str] = []

udp_bot_telemetry_buffer: list[dict] = []
bot_telemetry_clients: set[WebSocket] = set()


accumulator = Accumulator(window_size=ACC_WIND_SIZE)

class TelemetryUDPProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, add: tuple[str, int]):
        try:
            text = data.decode("utf-8")
            metrics = text.splitlines()

            # accumulator API usage
            accumulator.accumulate(metrics)
            
        except (UnicodeDecodeError, ValueError):
            print(f"Invalid telemetry packet from {add}")

class ExchangeUDPProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr: tuple[str, int]):
        parsed_book = parse_binary_market_packet(data)

        if parsed_book:
            market_data["bids"] = parsed_book["bids"]
            market_data["asks"] = parsed_book["asks"]

            udp_message_buffer.append(parsed_book)

async def broadcast_bot_telemetry():

    while True:
        await asyncio.sleep(0.002)

        # accumulator API usage 
        metrics = accumulator.get_metrics()

        payload = json.dumps(
            {
                "type": "BOT_TELE_BATCH",
                "timestamp": time.time(),
                "metrics": metrics
            }
        )

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
        # reset the buffer
        udp_message_buffer = []

        payload = json.dumps(
            {
                "type": "MARKET_DATA_BATCH",
                "timestamp": time.time(),
                "snapshot" : market_data,
                "updates": current_batch,
            }
        )

        disconnected_clients = set()
        for client in list(market_clients):
            try:
                await client.send_text(payload)
            except Exception:
                disconnected_clients.add(client)

        # Cleans up dropped connections
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

    broadcast_task = asyncio.create_task(
        broadcast_market_data()
    )

    broadcast_tele_bot = asyncio.create_task(
        broadcast_bot_telemetry()
    )

    try:
        yield

    finally:

        broadcast_task.cancel()
        broadcast_tele_bot.cancel()

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