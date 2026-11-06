"""Servidor web: serve o front-end e transmite a simulação via WebSocket.

Rodar: uvicorn app.main:app --reload
Abrir: http://127.0.0.1:8000
"""
import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent.environment import DIRECTIONS
from agent.simulation import Simulation

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Agente de Controle de Trânsito")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    """Cada aba do navegador ganha sua própria simulação."""
    await websocket.accept()
    state = {"sim": Simulation(seed=7), "paused": False, "delay": 1.5}

    async def run_loop():
        while True:
            if not state["paused"]:
                await websocket.send_json(state["sim"].step())
            await asyncio.sleep(state["delay"])

    loop_task = asyncio.create_task(run_loop())
    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("cmd") == "step":   # avanço manual de 1 tick (com pausa)
                await websocket.send_json(state["sim"].step())
            else:
                handle_command(state, msg)
    except WebSocketDisconnect:
        pass
    finally:
        loop_task.cancel()


def handle_command(state, msg):
    cmd, d = msg.get("cmd"), msg.get("dir")
    sim = state["sim"]
    if d is not None and d not in DIRECTIONS:
        return
    if cmd == "emergency":
        sim.inject_emergency(d)
    elif cmd == "fail_sensor":
        sim.fail_sensor(d)
    elif cmd == "repair_sensor":
        sim.repair_sensor(d)
    elif cmd == "surge":
        sim.set_surge(d, bool(msg.get("on")))
    elif cmd == "pause":
        state["paused"] = bool(msg.get("value"))
    elif cmd == "speed":
        state["delay"] = min(max(float(msg.get("value", 1.5)), 0.2), 3.0)
    elif cmd == "reset":
        state["sim"] = Simulation(seed=msg.get("seed"))
