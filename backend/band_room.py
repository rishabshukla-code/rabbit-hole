"""BAND transport for huddles (implementation B).

Each crew agent is a registered BAND remote agent with its own API key. A study session gets one
BAND room with the three agents (and their owner, so humans can watch). In a huddle every agent
reads the room history from BAND, thinks (Claude), and posts its message AS ITSELF with a real
@mention of the agent it addresses. Same shape as crew.huddle_local, so the session can fall back.
"""
import asyncio
import json
import logging
import re
import urllib.error
import urllib.request

import yaml

import crew
from config import ROOT

log = logging.getLogger("band")
CONFIG = ROOT / "backend" / "agent_config.yaml"
HOSTS = ["https://app.band.ai/api/v1/agent", "https://api.band.ai/api/v1/agent"]


def load_config() -> dict:
    if not CONFIG.exists():
        return {}
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return {a: v for a, v in cfg.items() if a in crew.AGENTS and v and v.get("agent_id") and v.get("api_key")}


def enabled() -> bool:
    return len(load_config()) == 3


class BandError(RuntimeError):
    pass


class Band:
    def __init__(self):
        self.cfg = load_config()
        self.host = None
        self.me: dict[str, dict] = {}

    def _call(self, agent: str, method: str, path: str, body=None, query: str = ""):
        hosts = [self.host] if self.host else HOSTS
        last = None
        for host in hosts:
            req = urllib.request.Request(
                f"{host}{path}{query}", method=method,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"X-API-Key": self.cfg[agent]["api_key"], "Content-Type": "application/json",
                         "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    self.host = host
                    return json.loads(r.read() or b"{}")
            except urllib.error.HTTPError as e:
                detail = e.read()[:300].decode(errors="replace")
                last = BandError(f"{method} {path} -> {e.code}: {detail}")
                if e.code not in (404, 503) or self.host:
                    raise last
            except (urllib.error.URLError, TimeoutError) as e:
                last = BandError(f"{method} {path} -> {e}")
        raise last

    async def call(self, *a, **k):
        return await asyncio.to_thread(self._call, *a, **k)

    async def connect(self):
        for a in crew.AGENTS:
            self.me[a] = (await self.call(a, "GET", "/me"))["data"]
        return {a: m["handle"] for a, m in self.me.items()}

    async def create_room(self, title: str) -> str:
        if not self.me:
            await self.connect()
        room = (await self.call("navigator", "POST", "/chats", {"chat": {"title": title[:120]}}))["data"]["id"]
        for a in ("professor", "examiner"):
            await self.call("navigator", "POST", f"/chats/{room}/participants",
                            {"participant": {"participant_id": self.me[a]["id"], "role": "member"}})
        try:  # add the human owner so the huddle can be watched live in the BAND app
            await self.call("navigator", "POST", f"/chats/{room}/participants",
                            {"participant": {"participant_id": self.me["navigator"]["owner_uuid"], "role": "member"}})
        except BandError as e:
            log.info("could not add owner to room: %s", e)
        return room

    async def post(self, room: str, agent: str, text: str, to: list[str]):
        # address `to`, but mention every other crew member: BAND only delivers a message to the agents it
        # mentions, and each agent must see the whole huddle when it reads the room history
        to = [t for t in to if t != agent and t in self.me] or [next(a for a in crew.AGENTS if a != agent)]
        to += [a for a in crew.AGENTS if a != agent and a not in to]
        text = re.sub(r"@all\b[:,]?\s*", "", text, flags=re.I)  # real mentions already reach everyone
        for t in to:  # the model writes @professor; BAND wants the agent's display name
            text = re.sub(rf"@{t}\b", f"@{self.me[t]['name']}", text, flags=re.I)
        missing = [f"@{self.me[t]['name']}" for t in to if f"@{self.me[t]['name']}" not in text]
        content = (" ".join(missing) + " " + text).strip() if missing else text
        mentions = [{"id": self.me[t]["id"], "name": self.me[t]["name"]} for t in to]
        return await self.call(agent, "POST", f"/chats/{room}/messages",
                               {"message": {"content": content, "mentions": mentions}})

    async def history(self, room: str, agent: str) -> list[dict]:
        res = await self.call(agent, "GET", f"/chats/{room}/messages", query="?status=all&sort_order=asc&limit=100")
        agent_by_id = {m["id"]: a for a, m in self.me.items()}
        names = {m["id"]: m["name"] for m in self.me.values()}
        unmark = lambda s: re.sub(r"@\[\[([0-9a-fA-F-]+)\]\]", lambda g: "@" + names.get(g.group(1), "agent"), s or "")
        return [{"from": agent_by_id[x["sender_id"]], "text": unmark(x.get("content"))}
                for x in res.get("data", []) if x.get("sender_id") in agent_by_id]


def _addressees(turn: dict, nxt: str | None, first: str) -> list[str]:
    if turn["to"] in crew.AGENTS:
        return [turn["to"]]
    return [nxt or first]


async def huddle_band(band: Band, room: str, trigger: str, situation: dict, memory_notes: dict, on_message) -> dict:
    order = [crew.FIRST[trigger]] + [a for a in crew.AGENTS if a != crew.FIRST[trigger]]
    turns = []
    for i, agent in enumerate(order):
        try:
            hist = await band.history(room, agent)
            transcript = [{"agent": h["from"], "text": h["text"]} for h in hist][-8:]
        except BandError as e:
            log.warning("history failed, using local transcript: %s", e)
            transcript = [{"agent": t["agent"], "text": t["text"]} for t in turns]
        turn = await crew.agent_turn(agent, trigger, situation, transcript, memory_notes.get(agent, ""))
        turn["agent"] = agent
        nxt = order[i + 1] if i + 1 < len(order) else None
        try:
            await band.post(room, agent, turn["text"], _addressees(turn, nxt, order[0]))
            turn["via"] = "band"
        except BandError as e:
            log.warning("post failed: %s", e)
            turn["via"] = "local"
        turns.append(turn)
        await on_message(turn)
    decision = crew.tally(trigger, turns)
    try:
        others = [a for a in crew.AGENTS if a != order[0]]
        await band.post(room, order[0], f"DECISION: {decision['decision']} (agreed by {', '.join(decision['agreed_by'])}). "
                                        f"Reason: {decision['reason']}", others)
    except BandError as e:
        log.warning("decision post failed: %s", e)
    decision["via"] = "band" if all(t.get("via") == "band" for t in turns) else "mixed"
    return decision
