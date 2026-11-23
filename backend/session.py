"""One study session: holes, triggers (code decides WHEN), huddles (agents decide WHAT), quizzes, report."""
import asyncio
import logging
import re
import time
import uuid

import band_room
import crew
import pipeline
from config import HOLE_LIMIT_S, HUDDLE_COOLDOWN_S, MODEL, OFFLINE, SKIM_S_PER_100_WORDS
from pipeline import log_event

log = logging.getLogger("session")


class Session:
    def __init__(self, send):
        self._send = send
        self._send_lock = asyncio.Lock()
        self.lock = asyncio.Lock()
        self.id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.started = self.ended = False
        self.busy = False
        self.sections, self.concepts = [], []
        self.goal, self.budget_s = "task", 300
        self.t0 = 0.0
        self.cur = 0
        self.section_entered = 0.0
        self.finished, self.quizzed = set(), set()
        self.holes: dict[str, dict] = {}
        self.current: str | None = None
        self.parking_lot: list[dict] = []
        self.pending_quiz: dict | None = None
        self.last_huddle = 0.0
        self.memory = {"policy": {}, "scores": {}, "profile": [], "sessions": 0}
        self.notes: dict[str, str] = {}
        self.band = None
        self.band_room: str | None = None
        self.band_info: dict = {"enabled": False}

    async def send(self, msg: dict):
        async with self._send_lock:
            await self._send(msg)

    # ------------------------------------------------------------ helpers
    def now(self):
        return time.time()

    def time_left(self):
        return max(0.0, self.budget_s - (self.now() - self.t0))

    def tolerance(self, category):
        return int(self.memory["policy"].get(category, {}).get("depth_tolerance", 0) or 0)

    def time_factor(self, category):
        return float(self.memory["policy"].get(category, {}).get("time_factor", 1.0) or 1.0)

    def concept_info(self, name: str) -> dict | None:
        return next((c for c in self.concepts if c["name"] == name), None) or crew.match_concept(name, self.concepts)

    def used_later(self, hole) -> bool:
        info = self.concept_info(hole["concept"])
        if info and info.get("used_later"):
            return True
        names = [hole["concept"]] + ([a for a in (info.get("aliases") or "").split("|") if a] if info else [])
        later = " ".join(s["text"].lower() for s in self.sections[hole["section_idx"] + 1:])
        return any(n and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", later) for n in names)

    def build_notes(self):
        pol = [p["note"] for p in self.memory["policy"].values() if p.get("note") and "default" not in p["note"]]
        notes = {}
        for a in crew.AGENTS:
            s = self.memory["scores"].get(a)
            parts = list(pol)
            if s:
                parts.append(f"Your past calls were right {round((s['accuracy'] or 0) * 100)}% of the time over {s['decisions']} decisions.")
                if s.get("good_examples"):
                    parts.append("Decisions of yours that worked: " + s["good_examples"])
                if s.get("bad_examples"):
                    parts.append("Decisions of yours that backfired: " + s["bad_examples"])
            notes[a] = " ".join(parts)
        self.notes = notes

    def exit_hole(self, reason="leave"):
        if not self.current:
            return
        h = self.holes[self.current]
        log_event(self.id, "hole_exit", concept=h["concept"], category=h["category"], section_idx=h["section_idx"],
                  duration_s=round(self.now() - h["entered_at"], 1), text=reason)
        self.current = None

    # ------------------------------------------------------------ start
    async def start(self, material: str, goal: str, minutes: float):
        self.goal = goal if goal in ("gist", "task", "exam") else "task"
        self.budget_s = max(60, int(float(minutes) * 60))
        await self.send({"type": "status", "text": "Bruin is reading your material..."})
        run, self.sections, self.concepts = await pipeline.prepare_material(self.id, material, self.goal)
        if not self.sections:
            await self.send({"type": "error", "text": "Couldn't build a map from that text. Try the demo chapter."})
            return
        self.memory = pipeline.load_memory()
        self.build_notes()
        if band_room.enabled():
            try:
                self.band = band_room.Band()
                handles = await self.band.connect()
                self.band_room = await self.band.create_room(f"Rabbit Hole huddles · {self.id}")
                self.band_info = {"enabled": True, "room": self.band_room, "handles": handles}
            except Exception as e:
                log.warning("BAND unavailable, huddles run locally: %s", e)
                self.band_info = {"enabled": False, "error": str(e)[:200]}
        self.started, self.t0 = True, self.now()
        self.cur, self.section_entered = 0, self.now()
        log_event(self.id, "session_start", count=len(self.sections), goal=self.goal)
        log_event(self.id, "section_enter", section_idx=0)
        welcome = None
        if self.memory["sessions"]:
            welcome = {"sessions": self.memory["sessions"],
                       "notes": [p["note"] for p in self.memory["policy"].values() if p.get("note")],
                       "profile": [{"category": p["category"], "over_dig_rate": round(p["over_dig_rate"] or 0, 2)}
                                   for p in self.memory["profile"]],
                       "scores": {a: round((s["accuracy"] or 0) * 100) for a, s in self.memory["scores"].items()}}
        await self.send({"type": "session", "session_id": self.id, "goal": self.goal, "budget_s": self.budget_s,
                         "sections": self.sections, "concepts": self.concepts, "pipeline": run, "welcome": welcome,
                         "llm": {"offline": OFFLINE, "model": MODEL}, "band": self.band_info})

    # ------------------------------------------------------------ messages from the browser
    async def handle(self, msg: dict):
        kind = msg.get("type")
        if kind == "start":
            return await self.start(msg.get("material", ""), msg.get("goal", "task"), msg.get("minutes", 5))
        if kind == "explore" and self.ended:     # after the session: free digging, no crew interruptions
            res = await crew.ask(msg.get("text", ""), section=self.sections[0], goal="exam", concepts=self.concepts,
                                 hole={"concept": msg.get("concept", ""), "depth": 2}, history=[])
            return await self.send({"type": "explore_answer", "concept": msg.get("concept"), "answer": res["answer"]})
        if not self.started or self.ended:
            return
        if self.busy and kind not in ("ping",):
            return await self.send({"type": "busy", "text": "The crew is huddling..."})
        async with self.lock:
            if kind == "ask":
                await self.on_ask((msg.get("text") or "").strip())
            elif kind == "goto":
                await self.on_goto(int(msg.get("idx", 0)))
            elif kind == "climb_out":
                if self.current:
                    self.exit_hole("climbed out")
                    await self.send({"type": "avatar", "action": "climb_out"})
            elif kind == "override":
                await self.on_override(msg.get("concept"))
            elif kind == "quiz_answer":
                await self.on_quiz_answer((msg.get("text") or "").strip())
            elif kind == "finish":
                await self.end("finished")

    async def on_ask(self, text: str):
        if not text:
            return
        section = self.sections[self.cur]
        hole = self.holes.get(self.current) if self.current else None
        await self.send({"type": "thinking", "agent": "professor"})
        res = await crew.ask(text, section=section, goal=self.goal, concepts=self.concepts, hole=hole,
                             history=hole["qa"] if hole else [])
        name = (res["concept"] or "this").strip().lower()
        info = self.concept_info(name)
        if info:
            name = info["name"]
        if hole and (res["is_followup"] or name == hole["concept"]):
            name = hole["concept"]
            info = self.concept_info(name)
        if self.current and name != self.current:
            self.exit_hole("new question")
        h = self.holes.get(name)
        if h is None:
            h = self.holes[name] = {
                "concept": name, "category": info["category"] if info else res["category_estimate"],
                "required": info["required_depth"] if info else res["required_depth_estimate"],
                "source": "pipeline" if info else "live", "section_idx": self.cur, "depth": 0, "max_depth": 0,
                "entered_at": self.now(), "parked": False, "extra": 0, "answers_left": None,
                "too_long_fired": False, "overrides": 0, "qa": []}
        elif self.current != name:
            h["entered_at"] = self.now()
            h["too_long_fired"] = False
        self.current = name
        if h["parked"]:
            await self.send({"type": "crew_msg", "agent": "navigator", "to": "user", "emotion": "neutral", "solo": True,
                             "text": f"'{name}' is in your Parking Lot for after the session. Press 'I really need this' if you truly do."})
            await self.send({"type": "parked_blocked", "concept": name})
            return
        depth = max(int(res["depth"]), h["depth"] if res["is_followup"] else 1)
        h["depth"], h["max_depth"] = depth, max(h["max_depth"], depth)
        h["qa"].append({"q": text, "a": res["answer"], "depth": depth})
        limit = h["required"] + self.tolerance(h["category"]) + h["extra"]
        log_event(self.id, "question_asked", concept=name, category=h["category"], depth=depth,
                  required_depth=h["required"], is_followup=bool(res["is_followup"]), section_idx=self.cur, text=text)
        await self.send({"type": "answer", "agent": "professor", "concept": name, "depth": depth,
                         "required": h["required"], "limit": limit, "category": h["category"],
                         "answer": res["answer"], "depth_hint": res["depth_hint"], "emotion": res["emotion"],
                         "section_idx": self.cur, "over": depth > limit, "src": res.get("_src")})
        if h["answers_left"] is not None:            # "one more, then park" was agreed
            h["answers_left"] -= 1
            if h["answers_left"] < 0:
                await self.send({"type": "crew_msg", "agent": "navigator", "to": "user", "emotion": "agree", "solo": True,
                                 "text": f"That was the extra answer we agreed on. Parking '{name}' now."})
                return await self.apply("park", h)
        if depth > limit:
            if self.now() - self.last_huddle >= HUDDLE_COOLDOWN_S:
                await self.huddle("over_depth", h)

    async def on_goto(self, idx: int):
        idx = max(0, min(idx, len(self.sections) - 1))
        if idx == self.cur:
            return
        prev, dur = self.cur, self.now() - self.section_entered
        self.exit_hole("moved on")
        forward = idx == prev + 1
        if forward:
            self.finished.add(prev)
            log_event(self.id, "section_finish", section_idx=prev, duration_s=round(dur, 1))
        self.cur, self.section_entered = idx, self.now()
        log_event(self.id, "section_enter", section_idx=idx)
        await self.send({"type": "moved", "idx": idx})
        if forward:
            sec = self.sections[prev]
            skim_limit = sec["word_count"] / 100 * SKIM_S_PER_100_WORDS
            if dur < skim_limit and prev not in self.quizzed and self.now() - self.last_huddle >= HUDDLE_COOLDOWN_S:
                await self.huddle("skimmed", None, section_idx=prev, seconds=round(dur, 1))
            elif sec.get("is_key") and prev not in self.quizzed:
                await self.start_quiz(prev, "key section")

    async def on_override(self, concept):
        h = self.holes.get(concept or "")
        if not h or not h["parked"]:
            return
        h["parked"], h["answers_left"], h["overrides"] = False, 0, h["overrides"] + 1
        self.parking_lot = [p for p in self.parking_lot if p["concept"] != h["concept"]]
        self.current, h["entered_at"] = h["concept"], self.now()
        log_event(self.id, "override", concept=h["concept"], category=h["category"], section_idx=h["section_idx"])
        await self.send({"type": "override_ok", "concept": h["concept"], "parking_lot": self.parking_lot})
        await self.send({"type": "crew_msg", "agent": "navigator", "to": "user", "emotion": "neutral", "solo": True,
                         "text": f"Okay, one more on '{h['concept']}'. Noted - the crew learns from this."})

    # ------------------------------------------------------------ huddles and decisions
    def situation(self, trigger, h, **extra):
        base = {"goal": self.goal, "time_left_s": int(self.time_left()), "sections_done": len(self.finished),
                "sections_total": len(self.sections),
                "upcoming_sections": [s["title"] for s in self.sections[self.cur + 1:]], **extra}
        if h:
            base.update({"concept": h["concept"], "category": h["category"], "depth": h["depth"],
                         "required_depth": h["required"], "extra_tolerance_learned": self.tolerance(h["category"]),
                         "seconds_in_hole": int(self.now() - h["entered_at"]), "used_later": self.used_later(h),
                         "learner_questions": [q["q"] for q in h["qa"]][-4:], "overrides_on_this": h["overrides"]})
        return base

    async def huddle(self, trigger: str, h: dict | None, **extra):
        self.busy = True
        try:
            sit = self.situation(trigger, h, **extra)
            await self.send({"type": "huddle_start", "trigger": trigger, "concept": h and h["concept"],
                             "first": crew.FIRST[trigger]})

            async def on_message(turn):
                await self.send({"type": "crew_msg", "agent": turn["agent"], "to": turn["to"], "text": turn["text"],
                                 "emotion": turn["emotion"], "vote": turn["vote"], "src": turn.get("_src"),
                                 "via": turn.get("via", "local")})

            d = None
            if self.band_room:
                try:
                    d = await band_room.huddle_band(self.band, self.band_room, trigger, sit, self.notes, on_message)
                except Exception as e:  # BAND down mid-demo: finish this huddle locally
                    log.warning("BAND huddle failed, falling back to local: %s", e)
            if d is None:
                d = await crew.huddle_local(trigger, sit, self.notes, on_message)
                d["via"] = "local"
            log_event(self.id, "huddle", trigger=trigger, decision=d["decision"], agreed_by=",".join(d["agreed_by"]),
                      concept=h and h["concept"], category=h and h["category"],
                      section_idx=h["section_idx"] if h else extra.get("section_idx"), text=d["reason"])
            await self.send({"type": "decision", "trigger": trigger, "concept": h and h["concept"], **d})
            await self.apply(d["decision"], h, section_idx=extra.get("section_idx"))
        finally:
            self.last_huddle = self.now()
            self.busy = False
            await self.send({"type": "huddle_end"})

    async def apply(self, decision: str, h: dict | None, section_idx=None):
        if decision == "park" and h:
            h["parked"], h["answers_left"] = True, None
            q = h["qa"][-1]["q"] if h["qa"] else h["concept"]
            self.parking_lot.append({"concept": h["concept"], "question": q, "depth": h["depth"]})
            log_event(self.id, "park", concept=h["concept"], category=h["category"], section_idx=h["section_idx"])
            if self.current == h["concept"]:
                self.exit_hole("parked")
            await self.send({"type": "park", "concept": h["concept"], "question": q, "parking_lot": self.parking_lot})
        elif decision == "one_more" and h:
            h["answers_left"] = 0
            h["extra"] = max(h["extra"], 3)          # the next answer is allowed at any depth
        elif decision == "continue" and h:
            h["extra"] = max(h["extra"], h["depth"] - h["required"] - self.tolerance(h["category"]))
        elif decision == "quiz":
            idx = section_idx if section_idx is not None else (h["section_idx"] if h else self.cur)
            await self.start_quiz(idx, "huddle", hole=h["concept"] if h else None)

    # ------------------------------------------------------------ quizzes
    async def start_quiz(self, idx: int, why: str, hole: str | None = None):
        self.quizzed.add(idx)
        sec = self.sections[idx]
        await self.send({"type": "thinking", "agent": "examiner"})
        q = await crew.quiz_question(sec, self.goal)
        self.pending_quiz = {"section_idx": idx, "question": q["question"], "why": why, "hole": hole}
        log_event(self.id, "quiz_asked", section_idx=idx, text=q["question"])
        await self.send({"type": "quiz", "agent": "examiner", "section_idx": idx, "question": q["question"], "why": why})

    async def on_quiz_answer(self, text: str):
        pq = self.pending_quiz
        if not pq:
            return
        self.pending_quiz = None
        sec = self.sections[pq["section_idx"]]
        await self.send({"type": "thinking", "agent": "examiner"})
        g = await crew.grade(sec, pq["question"], text)
        log_event(self.id, "quiz_graded", section_idx=pq["section_idx"], grade=g["grade"], text=text)
        await self.send({"type": "quiz_result", "agent": "examiner", "section_idx": pq["section_idx"], **g})
        h = self.holes.get(pq["hole"] or "")
        if h and not h["parked"]:
            if g["grade"] == "got_it":
                await self.apply("continue", h)
            else:
                await self.send({"type": "crew_msg", "agent": "navigator", "to": "user", "emotion": "neutral", "solo": True,
                                 "text": "Let's lock in the basics first. Parking the deeper part for later."})
                await self.apply("park", h)

    # ------------------------------------------------------------ timer and end
    async def tick(self):
        if not self.started or self.ended or self.busy or self.lock.locked():
            return
        if self.time_left() <= 0:
            async with self.lock:
                return await self.end("time")
        h = self.holes.get(self.current) if self.current else None
        if h and not h["parked"] and not h["too_long_fired"]:
            limit = HOLE_LIMIT_S * self.time_factor(h["category"])
            if self.now() - h["entered_at"] > limit and self.now() - self.last_huddle >= HUDDLE_COOLDOWN_S:
                h["too_long_fired"] = True
                async with self.lock:
                    await self.huddle("too_long", h)

    async def end(self, why: str):
        if self.ended:
            return
        self.ended = True
        self.exit_hole("session end")
        if why == "finished":
            self.finished.add(self.cur)
            log_event(self.id, "section_finish", section_idx=self.cur, duration_s=round(self.now() - self.section_entered, 1))
        log_event(self.id, "session_end", duration_s=round(self.now() - self.t0, 1), text=why)
        await self.send({"type": "ending", "why": why, "text": "The crew is writing your report..."})
        run, report, digs = await pipeline.analyze_session(self.id)
        memory_after = pipeline.load_memory()
        comments = await crew.final_comments(report, digs, self.notes)
        next_time = [p["note"] for p in memory_after["policy"].values() if p.get("note")]
        await self.send({"type": "report", "report": report, "holes": digs, "parking_lot": self.parking_lot,
                         "comments": comments, "pipeline": run, "next_time": next_time,
                         "scores": {a: {"accuracy": round((s["accuracy"] or 0) * 100), "decisions": s["decisions"]}
                                    for a, s in memory_after["scores"].items()}})
