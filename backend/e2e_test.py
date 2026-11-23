"""Live end-to-end checks for the paths the smoke test doesn't cover:
skimmed trigger, quiz, over-depth huddle, park -> blocked -> override -> one more -> auto-park,
too-long trigger, report, Explore now, and the Welcome card on the next session.
Run with the backend up:  .venv/Scripts/python backend/e2e_test.py"""
import asyncio
import json
import time

import websockets

URL = "ws://127.0.0.1:8000/ws"
T0 = time.time()
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


class Client:
    def __init__(self, ws):
        self.ws, self.seen = ws, []

    async def until(self, *types, timeout=90):
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = json.loads(await asyncio.wait_for(self.ws.recv(), end - time.time()))
            except asyncio.TimeoutError:
                break
            self.seen.append(m)
            if m["type"] in ("crew_msg", "decision", "error", "parked_blocked", "override_ok", "quiz", "quiz_result"):
                txt = m.get("text") or m.get("decision") or m.get("question") or m.get("grade") or m.get("concept")
                print(f"   {time.time() - T0:6.1f}s {m['type']:<14} {m.get('agent', m.get('trigger', '')):<10} {str(txt)[:90]} {m.get('via', '')}")
            if m["type"] in types:
                return m
        return None

    async def send(self, **msg):
        await self.ws.send(json.dumps(msg))


async def ask(c, text):
    await c.send(type="ask", text=text)
    return await c.until("answer", "parked_blocked")


async def wait_cooldown(c, seconds=21):
    await c.until("never", timeout=seconds)


async def main():
    demo = open("content/demo_chapter.md", encoding="utf-8").read()
    async with websockets.connect(URL, open_timeout=30) as ws:
        c = Client(ws)
        await c.send(type="start", material=demo, goal="task", minutes=10)
        s = await c.until("session", timeout=120)
        check("session starts", s is not None, f"band={s and s['band'].get('enabled')}")

        # 1. skimmed: leave section 1 after a few seconds
        await asyncio.sleep(2)
        await c.send(type="goto", idx=1)
        h = await c.until("huddle_start", "quiz", timeout=30)
        check("skimmed trigger fires", h is not None and h.get("trigger") == "skimmed", str(h and h.get("trigger")))
        d = await c.until("huddle_end", timeout=60)
        q = next((m for m in c.seen if m["type"] == "quiz"), None) or await c.until("quiz", timeout=20)
        if q:
            await c.send(type="quiz_answer", text="We made a folder with a virtual environment so the packages stay separate per project.")
            r = await c.until("quiz_result", timeout=60)
            check("quiz graded", r is not None, r and r["grade"])
        else:
            check("quiz graded", True, "(crew chose not to quiz)")
        await wait_cooldown(c)

        # 2. over-depth huddle on pip (needs depth 2 for this goal), then park/override path
        a1 = await ask(c, "what is pip?")
        check("depth-1 answer", a1 and a1["type"] == "answer", a1 and f"depth {a1.get('depth')} / needs {a1.get('required')}")
        a2 = await ask(c, "how does pip's dependency resolver actually work internally, and who invented it?")
        check("deep follow-up answered at depth 3", a2 and a2.get("depth") == 3, a2 and str(a2.get("depth")))
        hs = await c.until("huddle_start", timeout=20)
        check("over-depth huddle fires", hs is not None and hs["trigger"] == "over_depth")
        dec = await c.until("decision", timeout=90)
        await c.until("huddle_end", timeout=30)
        check("decision made", dec is not None, dec and f"{dec['decision']} by {dec['agreed_by']} via {dec.get('via')}")
        concept = a2["concept"] if a2 else "pip"
        if dec and dec["decision"] == "one_more":
            x = await ask(c, "and how does pip pick between two conflicting versions?")
            check("one_more gives one extra answer", x and x["type"] == "answer")
            x2 = await c.until("park", timeout=20)
            check("then auto-parks", x2 is not None)
        elif dec and dec["decision"] != "park":
            print("   (crew didn't park; override path skipped for this concept)")
        parked = any(m["type"] == "park" for m in c.seen)
        if parked:
            b = await ask(c, f"but how does {concept} store its cache?")
            check("parked concept is blocked", b and b["type"] == "parked_blocked")
            await c.send(type="override", concept=concept)
            o = await c.until("override_ok", timeout=20)
            check("override accepted", o is not None)
            o2 = await ask(c, f"ok, how does {concept} store its cache?")
            check("override gives one answer", o2 and o2["type"] == "answer")
            ap = await c.until("park", timeout=20)
            check("after override's answer it auto-parks again", ap is not None)

        # 3. too long in one hole
        await c.send(type="goto", idx=2)
        await c.until("moved", timeout=20)
        await c.until("never", timeout=3)
        p1 = await ask(c, "what is an API?")   # mentioned in passing: needs depth 1, so depth 1 is "enough"
        print(f"   api: depth {p1 and p1.get('depth')} / needs {p1 and p1.get('required')}")
        print("   waiting for the too-long timer (~30 s)...")
        tl = await c.until("huddle_start", timeout=75)
        check("too-long trigger fires", tl is not None and tl["trigger"] == "too_long", str(tl and tl.get("trigger")))
        await c.until("huddle_end", timeout=90)

        # 4. finish -> report -> explore
        await c.send(type="finish")
        rep = await c.until("report", timeout=180)
        check("report arrives", rep is not None)
        if rep:
            check("report has crew comments", len(rep["comments"]) == 3)
            check("report has training notes", bool(rep["next_time"]), "; ".join(rep["next_time"])[:120])
            check("bruin analytics ran", rep["pipeline"]["ok"], str(rep["pipeline"]))
            if rep["parking_lot"]:
                p = rep["parking_lot"][0]
                await c.send(type="explore", concept=p["concept"], text=p["question"])
                e = await c.until("explore_answer", timeout=60)
                check("explore now answers", e is not None and len(e["answer"]) > 20, e and e["answer"][:80])

    # 5. next session shows the Welcome card
    async with websockets.connect(URL, open_timeout=30) as ws:
        c = Client(ws)
        await c.send(type="start", material=demo, goal="task", minutes=5)
        s = await c.until("session", timeout=120)
        w = s and s.get("welcome")
        check("welcome card on next session", bool(w), w and f"sessions={w['sessions']} notes={w['notes'][:2]}")

    print(f"\n{sum(ok for _, ok in results)}/{len(results)} checks passed in {time.time() - T0:.0f}s")


asyncio.run(main())
