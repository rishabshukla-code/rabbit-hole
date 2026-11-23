"""Rabbit Hole backend: one WebSocket per study session."""
import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

import pipeline
from config import CONTENT, MODEL, OFFLINE
from session import Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")
app = FastAPI(title="Rabbit Hole")


@app.get("/api/health")
def health():
    return {"ok": True, "offline": OFFLINE, "model": MODEL}


@app.get("/api/demo", response_class=PlainTextResponse)
def demo():
    return (CONTENT / "demo_chapter.md").read_text(encoding="utf-8")


@app.get("/api/memory")
def memory():
    m = pipeline.load_memory()
    return {"sessions": m["sessions"],
            "notes": [p["note"] for p in m["policy"].values() if p.get("note")],
            "scores": {a: round((s["accuracy"] or 0) * 100) for a, s in m["scores"].items()}}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    session = Session(websocket.send_json)

    async def ticker():
        while True:
            await asyncio.sleep(2)
            try:
                await session.tick()
            except Exception:
                log.exception("tick failed")

    tick_task = asyncio.create_task(ticker())
    try:
        while True:
            msg = json.loads(await websocket.receive_text())
            # handle in a task so a long huddle never blocks reading the socket
            asyncio.create_task(_safe(session, msg, websocket))
    except WebSocketDisconnect:
        pass
    finally:
        tick_task.cancel()


async def _safe(session, msg, websocket):
    try:
        await session.handle(msg)
    except Exception as e:
        log.exception("handler failed")
        try:
            await websocket.send_json({"type": "error", "text": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
