from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import time
import uuid
import tempfile
import shutil
from pathlib import Path
import httpx

app = FastAPI()

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

def get_client_swarm_payload(submission_id: str) -> dict:

    template_data = (
        "{{ range service \"user-code-service\" }}\n"
        "SERVER_HOST = \"{{ .Address }}\"\n"
        "SERVER_PORT = \"{{ .Port }}\"\n"
        "{{ end }}"
    )

    return {
        "Job": {
            "ID": f"swarm-cluster-{submission_id}",
            "Name": f"swarm-cluster-{submission_id}",
            "Type": "service",
            "Datacenters": ["dc1"],
            "TaskGroups": [
                {
                    "Name": "market-makers",
                    "Count": 5,
                    "Tasks": [{
                        "Name": "swarm",
                        "Driver": "docker",
                        "Config": {"image": "localhost:5000/trading_bot:v1.0.0"},
                        "Templates": [{"EmbeddedTmpl": template_data, "DestPath": "secrets/env", "Envvars": True}],
                        "Env": {
                            "NUM_BOTS": "50", "PROB_BUY": "0.45", "PROB_SELL": "0.45", "PROB_CANCEL": "0.10",
                            "ASSET_INITIAL_PRICE": "50000", "STD_DEV": "2.5", "SLEEP_TIMEOUT": "0.005",
                            "TELEMETRY_HOST": "${attr.unique.network.ip-address}", "TELEMETRY_PORT": "8125"
                        },
                        "Resources": {"CPU": 1500, "MemoryMB": 512}
                    }]
                },
                {
                    "Name": "trend-followers",
                    "Count": 5,
                    "Tasks": [{
                        "Name": "swarm",
                        "Driver": "docker",
                        "Config": {"image": "localhost:5000/trading_bot:v1.0.0"},
                        "Templates": [{"EmbeddedTmpl": template_data, "DestPath": "secrets/env", "Envvars": True}],
                        "Env": {
                            "NUM_BOTS": "50", "PROB_BUY": "0.75", "PROB_SELL": "0.15", "PROB_CANCEL": "0.10",
                            "ASSET_INITIAL_PRICE": "50000", "STD_DEV": "5.0", "SLEEP_TIMEOUT": "0.015",
                            "TELEMETRY_HOST": "${attr.unique.network.ip-address}", "TELEMETRY_PORT": "8125"
                        },
                        "Resources": {"CPU": 1500, "MemoryMB": 512}
                    }]
                },
                {
                    "Name": "liquidators",
                    "Count": 5,
                    "Tasks": [{
                        "Name": "swarm",
                        "Driver": "docker",
                        "Config": {"image": "localhost:5000/trading_bot:v1.0.0"},
                        "Templates": [{"EmbeddedTmpl": template_data, "DestPath": "secrets/env", "Envvars": True}],
                        "Env": {
                            "NUM_BOTS": "50", "PROB_BUY": "0.15", "PROB_SELL": "0.75", "PROB_CANCEL": "0.10",
                            "ASSET_INITIAL_PRICE": "50000", "STD_DEV": "4.0", "SLEEP_TIMEOUT": "0.01",
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
                        
                        # opens up the host machine interface to listen to port 8888 and
                        # routes traffic into gVisor's Netstack
                        "Networks": [
                            {
                                "Mode": "host",
                                "ReservedPorts": [
                                    {
                                        "label": "exchange_port",
                                        "Value": 8888
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

