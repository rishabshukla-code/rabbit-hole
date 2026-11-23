"""Plays a short scripted session over the WebSocket and prints what the crew does."""
import asyncio, json, sys
import websockets

async def main(url="ws://127.0.0.1:8000/ws"):
    async with websockets.connect(url) as ws:
        async def recv_until(*types, timeout=120):
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                t = m["type"]
                short = {k: v for k, v in m.items() if k not in ("sections", "concepts")}
                print(f"  <- {t}: {json.dumps(short, default=str)[:230]}")
                if t in types:
                    return m
        demo = open("content/demo_chapter.md", encoding="utf-8").read()
        await ws.send(json.dumps({"type": "start", "material": demo, "goal": "task", "minutes": 5}))
        s = await recv_until("session", "error")
        print("sections:", [x["title"] for x in s["sections"]], "concepts:", len(s["concepts"]))
        await ws.send(json.dumps({"type": "ask", "text": "what's a virtual environment?"}))
        await recv_until("answer")
        await ws.send(json.dumps({"type": "ask", "text": "but how does it keep packages separate internally?"}))
        await recv_until("huddle_end")
        await ws.send(json.dumps({"type": "ask", "text": "why was it invented?"}))
        await asyncio.sleep(1.5)
        await ws.send(json.dumps({"type": "goto", "idx": 1}))
        await recv_until("quiz", "moved")
        await ws.send(json.dumps({"type": "finish"}))
        r = await recv_until("report", timeout=240)
        print("COMMENTS:", [c["comment"][:80] for c in r["comments"]])
        print("NEXT TIME:", r["next_time"])

asyncio.run(main(*sys.argv[1:]))
