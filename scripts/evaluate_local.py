"""Exercise cached models on a user-supplied labeled photo manifest."""

import argparse
import json
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient
from wardrobe.app import create_app
from wardrobe.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument(
    "manifest", type=Path, help='JSON list: {"path": "photo.jpg", "category": "tops"}'
)
parser.add_argument(
    "--data-dir",
    type=Path,
    required=True,
    help="Use a separate, empty evaluation directory",
)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if (args.data_dir / "wardrobe.sqlite3").exists():
    parser.error("Choose an empty data directory to keep the evaluation repeatable.")

original_connect = socket.socket.connect
connections = []


def local_connect(connection, address):
    if isinstance(address, tuple):
        connections.append(address[0])
        if address[0] not in ("127.0.0.1", "::1"):
            raise RuntimeError(f"External network access blocked: {address[0]}")
    return original_connect(connection, address)


socket.socket.connect = local_connect
report = {"recognition": [], "requests": [], "network": connections}
app = create_app(Settings(data_dir=args.data_dir))
with TestClient(app) as client:
    assert client.get("/").status_code == 200
    for photo in json.loads(args.manifest.read_text()):
        path = Path(photo["path"])
        started = time.perf_counter()
        response = client.post(
            "/api/items", files={"file": (path.name, path.read_bytes(), "image/jpeg")}
        )
        response.raise_for_status()
        item = response.json()
        report["recognition"].append(
            {
                "source": path.name,
                "expected": photo.get("category"),
                "item": item,
                "seconds": round(time.perf_counter() - started, 2),
            }
        )
    conversation = client.post("/api/conversations").json()
    prompts = [
        "Give me three business-casual options.",
        "Make these casual and do not use jeans.",
        "Use my blue button-down shirt in each option.",
        "Replace the shoes in option 2, keeping the rest of that outfit.",
        "Start fresh. Jeans are fine now. Give me three casual options.",
    ]
    for prompt in prompts:
        started = time.perf_counter()
        response = client.post(
            f"/api/conversations/{conversation['id']}/messages", json={"text": prompt}
        )
        result = response.json()
        report["requests"].append(
            {
                "prompt": prompt,
                "status": response.status_code,
                "seconds": round(time.perf_counter() - started, 2),
                "response": result,
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(
            prompt, response.status_code, report["requests"][-1]["seconds"], flush=True
        )
        if response.status_code != 200:
            print(result, flush=True)
print(f"Saved evaluation to {args.output}")
