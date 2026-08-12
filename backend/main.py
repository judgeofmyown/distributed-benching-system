import time
import uuid
import tempfile
import shutil
from pathlib import Path
import asyncio
import json
import httpx
from contextlib import asynccontextmanager
from market_viewer import parse_binary_market_packet
from fastapi.responses import JSONResponse
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect
import uvicorn

UDP_HOST = "0.0.0.0"
UDP_PORT = 9999
TELEMETRY_HOST = "0.0.0.0"
TELEMETRY_PORT = 8125
FLUSH_INTERVAL_SEC = 0.05

market_data = {"bids": [], "asks": []}
market_clients: set[WebSocket] = set()
udp_message_buffer: list[dict | str] = []

udp_bot_telemetry_buffer: list[dict] = []
bot_telemetry_clients: set[WebSocket] = set()

class TelemetryUDPProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, add: tuple[str, int]):
        try:
            text = data.decode("utf-8")
            metrics = text.splitlines()

            for metric in metrics:
                name, value_type = metric.split(":", 1)
                value, unit = value_type.split("|", 1)

                metric_data = {
                    "name" : name,
                    "value": value,
                    "unit": unit
                }
                udp_bot_telemetry_buffer.append(metric_data)
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
    global udp_bot_telemetry_buffer

    while True:
        await asyncio.sleep(0.002)

        if not udp_bot_telemetry_buffer:
            continue
        
        current_batch = udp_bot_telemetry_buffer
        udp_bot_telemetry_buffer = []

        payload = json.dumps(
            {
                "type": "BOT_TELE_BATCH",
                "timestamp": time.time(),
                "metrics": current_batch
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


NOMAD_URL = "http://127.0.0.1:4646/v1/jobs"
LOCAL_STORAGE_DIR = Path(tempfile.gettempdir()) / "nomad-submissions"
LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

RUNTIME_CONFIG = {
    ".py": {
        "image": "localhost:5000/py_build:v1.0.0",
        "command": None,
        "args":  None,
        "target_mount": "/app/submission"
    },
    ".cpp": {
        "image": "localhost:5000/cpp_build:v1.0.0",
        "command": None,
        "args":  None,
        "target_mount": "/app/submission"
    },
    ".go": {
        "image": "localhost:5000/go_build:v1.0.0",
        "command": None,
        "args":  None,
        "target_mount": "/app/submission"
    }
}

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

def get_client_swarm_payload(submission_id: str) -> dict:

    template_data = (
        '{{ range service "user-code-server" }}\n'
        'SERVER_HOST = "{{ .Address }}"\n'
        'SERVER_PORT = "{{ .Port }}"\n'
        '{{ end }}'
    )

    print(template_data)

    return {
        "Job": {
            "ID": f"swarm-cluster-{submission_id}",
            "Name": f"swarm-cluster-{submission_id}",
            "Type": "service",
            "Datacenters": ["dc1"],
            "TaskGroups": [
                {
                    "Name": "market-makers",
                    "Count": 3,
                    "Tasks": [{
                        "Name": "swarm",
                        "Driver": "docker",
                        "Config": {"image": "localhost:5000/trading_bot:v1.0.0", "network_mode": "host"},
                        "Templates": [{"EmbeddedTmpl": template_data, "DestPath": "secrets/env", "EnvVars": True}],
                        "Env": {
                            "NUM_BOTS": "50", "PROB_BUY": "30", "PROB_SELL": "30", "PROB_CANCEL": "10", "PROB_MARKET_BUY": "15","PROB_MARKET_SELL": "15",
                            "ASSET_INITIAL_PRICE": "50000", "STD_DEV": "1.5", "SLEEP_TIMEOUT": "1",
                            "TELEMETRY_HOST": "${attr.unique.network.ip-address}", "TELEMETRY_PORT": "8125"
                        },
                        "Resources": {"CPU": 1500, "MemoryMB": 512}
                    }]
                },
                {
                    "Name": "trend-followers",
                    "Count": 3,
                    "Tasks": [{
                        "Name": "swarm",
                        "Driver": "docker",
                        "Config": {"image": "localhost:5000/trading_bot:v1.0.0", "network_mode": "host"},
                        "Templates": [{"EmbeddedTmpl": template_data, "DestPath": "secrets/env", "EnvVars": True}],
                        "Env": {
                            "NUM_BOTS": "50", "PROB_BUY": "60", "PROB_SELL": "10", "PROB_CANCEL": "10",  "PROB_MARKET_BUY": "15","PROB_MARKET_SELL": "5",
                            "ASSET_INITIAL_PRICE": "50000", "STD_DEV": "2.2", "SLEEP_TIMEOUT": "1",
                            "TELEMETRY_HOST": "${attr.unique.network.ip-address}", "TELEMETRY_PORT": "8125"
                        },
                        "Resources": {"CPU": 1500, "MemoryMB": 512}
                    }]
                },
                {
                    "Name": "liquidators",
                    "Count": 3,
                    "Tasks": [{
                        "Name": "swarm",
                        "Driver": "docker",
                        "Config": {"image": "localhost:5000/trading_bot:v1.0.0", "network_mode": "host"},
                        "Templates": [{"EmbeddedTmpl": template_data, "DestPath": "secrets/env", "EnvVars": True}],
                        "Env": {
                            "NUM_BOTS": "50", "PROB_BUY": "10", "PROB_SELL": "60", "PROB_CANCEL": "10", "PROB_MARKET_BUY": "5","PROB_MARKET_SELL": "15",
                            "ASSET_INITIAL_PRICE": "50000", "STD_DEV": "2.0", "SLEEP_TIMEOUT": "2",
                            "TELEMETRY_HOST": "${attr.unique.network.ip-address}", "TELEMETRY_PORT": "8125"
                        },
                        "Resources": {"CPU": 1500, "MemoryMB": 512}
                    }]
                }
            ]
        }
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        filename = file.filename
        ext = Path(filename).suffix
        
        # canc check on ext for screening useless files
        if ext not in RUNTIME_CONFIG:
            return JSONResponse(
                status_code=400, 
                content={"message": f"Unsupported file extension context: {ext}"}
            )

        submission_id = str(uuid.uuid4())
        
        submission_dir = LOCAL_STORAGE_DIR / submission_id
        submission_dir.mkdir(parents=True, exist_ok=True)
        clean_source_path = str(submission_dir).replace("\\", "/")

        host_file_path = submission_dir / f"exchange_server{ext}"
        
        with host_file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        runtime = RUNTIME_CONFIG[ext]

        # payload for spining the user code execution job
        job_payload = {
            "Job": {
                "ID": f"submission-{submission_id}",
                "Name": f"submission-{submission_id}",
                "Type": "batch",
                "Datacenters": ["dc1"],
                "TaskGroups": [
                    {
                        "Name": "runner",
                        "Count": 1,
                        

                        "Networks": [
                            {
                                "ReservedPorts": [
                                    {
                                        "label": "exchange_port",
                                        "Value": 8080
                                    }
                                ]
                            }        
                        ],

                        # conul registration here--
                        "Services": [
                            {
                                "Name": "user-code-server",
                                "PortLabel": "exchange_port",
                                "Provider": "consul",
                                "Tags": [f"id-{submission_id}", "execution"]
                            }
                        ],

                        "Tasks": [
                            {
                                "Name": "executor",
                                "Driver": "docker",
                                "Env": {
                                    "NOMAD_IP": "0.0.0.0",
                                    "NOMAD_PORT": "8080"
                                },
                                "Config": {
                                    "image": runtime["image"],
                                    "runtime": "runc",
                                    "ports": ["exchange_port"],
                                    "mounts": [
                                        {
                                            "type": "bind",
                                            "target": runtime["target_mount"],
                                            "source": clean_source_path,
                                            "readonly": True
                                        }        
                                    ]
                                },
                                "Resources": {
                                    "CPU": 1000,
                                    "MemoryMB": 1024
                                },
                                "RestartPolicy": {
                                    "Attempts": 5,
                                    "Delay": 2000000000,
                                    "Interval": 60000000000,
                                    "Mode": "delay"                                
                                }
                            }
                        ]
                    }
                ]
            }
        }

        swarm_payload = get_client_swarm_payload(submission_id)

        async with httpx.AsyncClient() as client:
            # spining the user code server
            response = await client.post(NOMAD_URL, json=job_payload)
            if response.status_code != 200:
                return JSONResponse(status_code=500, content={"message": f"Nomad failed: {response.text}"})
            await asyncio.sleep(15) 
            swarm_res = await client.post(NOMAD_URL, json=swarm_payload)
            if swarm_res.status_code != 200:
                return JSONResponse(status_code=500, content={"message": f"Client swarm launch failed: {swarm_res.text}"})

        return {
                    "status": "success",
                    "submission_id": submission_id,
                    "saved_locally_at": str(host_file_path)
                }

    except Exception as e:
        return JSONResponse(status_code=500, content={"message": f"Upload file execution eror: {str(e)}"})

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