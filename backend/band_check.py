"""Checks the BAND setup on its own: keys valid, room creation, one @mention message from each agent.
Run:  .venv/Scripts/python backend/band_check.py"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import band_room  # noqa: E402


async def main():
    cfg = band_room.load_config()
    print("agents configured:", sorted(cfg), "(need professor, navigator, examiner)")
    if len(cfg) < 3:
        return
    b = band_room.Band()
    handles = await b.connect()
    print("host:", b.host)
    for a, h in handles.items():
        print(f"  {a}: {h}  id={b.me[a]['id']}")
    room = await b.create_room("Rabbit Hole · setup check")
    print("room created:", room)
    await b.post(room, "navigator", "Setup check: can you both hear me?", ["professor", "examiner"])
    await b.post(room, "professor", "Loud and clear.", ["navigator"])
    await b.post(room, "examiner", "Confirmed.", ["navigator"])
    for a in band_room.crew.AGENTS:
        print(f"history as {a}:", [(m["from"], m["text"][:40]) for m in await b.history(room, a)])
    print("BAND OK")


asyncio.run(main())
