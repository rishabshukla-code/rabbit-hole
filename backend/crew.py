"""The crew: three agents with conflicting goals. Each agent is its own Claude call with its own
system prompt; a huddle is a real back-and-forth where every agent sees the transcript so far,
@mentions the others, and votes. The decision is the majority vote."""
import asyncio
import json
import re

from llm import ask_json, obj

AGENTS = ["professor", "navigator", "examiner"]
EMOTIONS = ["worried", "excited", "skeptical", "agree", "neutral"]
DECISIONS = ["park", "one_more", "quiz", "continue"]

PERSONA = {
    "professor": (
        "You are the Professor, one of three AI study tutors who walk beside a learner in a 3D study world. "
        "Your goal: the learner UNDERSTANDS what this material actually needs. You answer the learner's questions. "
        "In huddles you defend a bit more depth ONLY when an upcoming section relies on the concept; otherwise you "
        "agree to park it. Warm, curious, concise."),
    "navigator": (
        "You are the Navigator, one of three AI study tutors who walk beside a learner in a 3D study world. "
        "Your goal: the learner FINISHES the material in their time budget. You watch the clock and the depth, and "
        "you push to park tangents and get them back on the path. Brisk and kind, never shaming: parked questions "
        "are saved for later, curiosity is good, the timing is the problem."),
    "examiner": (
        "You are the Examiner, one of three AI study tutors who walk beside a learner in a 3D study world. "
        "Your goal: the learner can PROVE they understood. Before granting more depth you want evidence they got "
        "the surface meaning; when they skim, you want a quick check. Dry, fair, a little skeptical."),
}

LEARNER = ("The learner (often someone with ADHD) is curious and capable but tends to dig far deeper into side "
           "concepts than the task needs, and then never finishes. Depth levels: 1 = what it is, "
           "2 = how to use it, 3 = how it works inside / why / history.")


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


# ---------------------------------------------------------------- asking a question (Professor)

ASK_SCHEMA = obj({
    "concept": {"type": "string"},
    "is_followup": {"type": "boolean"},
    "depth": {"type": "integer", "enum": [1, 2, 3]},
    "answer": {"type": "string"},
    "depth_hint": {"type": "string"},
    "emotion": {"type": "string", "enum": EMOTIONS},
    "category_estimate": {"type": "string", "enum": ["tooling", "theory", "history", "math", "other"]},
    "required_depth_estimate": {"type": "integer", "enum": [1, 2, 3]},
})

DEPTH_WORDS = [(3, r"\b(how does|how do .* work|why|internal|under the hood|history|who (made|invented)|invented)\b"),
               (2, r"\b(how (do|can|should) i|how to|use|command|install|example|set up|setup)\b"),
               (1, r"\b(what is|what's|what are|whats|meaning|mean|define)\b")]


def match_concept(text: str, concepts: list[dict]) -> dict | None:
    t = text.lower()
    best = None
    for c in concepts:
        names = [c["name"]] + [a for a in (c.get("aliases") or "").split("|") if a]
        for n in names:
            if n and re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", t):
                if best is None or len(n) > best[0]:
                    best = (len(n), c)
    return best[1] if best else None


async def ask(question: str, *, section: dict, goal: str, concepts: list[dict], hole: dict | None,
              history: list[dict]) -> dict:
    known = [{"name": c["name"], "aliases": c["aliases"], "required_depth": c["required_depth"],
              "category": c["category"]} for c in concepts]
    system = PERSONA["professor"] + " " + LEARNER + (
        " The learner just asked you a question while reading. Decide which concept it is about (use the exact "
        "known name when it matches one), whether it follows up on the concept they are currently digging into, "
        "and the DEPTH the question asks for. Answer at exactly that depth: depth 1 = one or two plain sentences; "
        "depth 2 = up to four sentences with a practical example; depth 3 = up to five sentences on internals. "
        "depth_hint = one short sentence on whether this depth is enough FOR THIS GOAL (e.g. 'For this tutorial, "
        "that's all you need.'). Never lecture; be kind.")
    user = _j({"goal": goal, "current_section": {"title": section["title"], "text": section["text"]},
               "known_concepts": known,
               "currently_digging": hole and {"concept": hole["concept"], "depth": hole["depth"]},
               "recent_questions_in_this_hole": history[-4:], "question": question})

    def fallback():
        c = match_concept(question, concepts)
        follow = hole is not None and (c is None or c["name"] == hole["concept"])
        if c is None and follow:
            c = next((k for k in concepts if k["name"] == hole["concept"]), None)
        depth = next((d for d, rx in DEPTH_WORDS if re.search(rx, question.lower())), 1)
        if follow and hole:
            depth = max(depth, min(3, hole["depth"] + 1))
        name = c["name"] if c else re.sub(r"^(what|how|why)\W+(is|are|does|do)?\s*", "", question.lower()).strip(" ?.")[:40] or "this"
        base = c["depth1_answer"] if c else f"{name.capitalize()} is a side detail of this section."
        answer = base if depth == 1 else (
            f"{base} In practice you mostly just run the command shown in the text and move on." if depth == 2
            else f"{base} Under the hood there's a lot more to it, but this tutorial never needs those internals.")
        need = c["required_depth"] if c else 1
        return {"concept": name, "is_followup": follow, "depth": depth, "answer": answer,
                "depth_hint": "For this tutorial, that's all you need." if depth >= need else "You'll use this, so it's worth knowing how.",
                "emotion": "excited" if depth <= need else "neutral",
                "category_estimate": c["category"] if c else "other", "required_depth_estimate": need}

    return await ask_json(system, user, ASK_SCHEMA, fallback, max_tokens=3000)


# ---------------------------------------------------------------- huddles

TURN_SCHEMA = obj({
    "to": {"type": "string", "enum": AGENTS + ["all"]},
    "text": {"type": "string"},
    "emotion": {"type": "string", "enum": EMOTIONS},
    "vote": {"type": "string", "enum": DECISIONS},
    "say_to_user": {"type": "string"},
    "reason": {"type": "string"},
})

FIRST = {"over_depth": "navigator", "too_long": "navigator", "skimmed": "examiner"}

TRIGGER_TEXT = {
    "over_depth": "The learner just dug deeper into a concept than this material needs for their goal.",
    "too_long": "The learner has been inside one rabbit hole for a long time.",
    "skimmed": "The learner finished a section very fast - they may have skimmed it.",
}


def _offline_vote(agent: str, trigger: str, sit: dict) -> dict:
    later = sit.get("used_later")
    if trigger == "skimmed":
        v = {"examiner": "quiz", "navigator": "continue", "professor": "quiz"}[agent]
    else:
        v = {"navigator": "park", "professor": "one_more" if later else "park",
             "examiner": "one_more" if later and sit.get("depth", 0) <= sit.get("required_depth", 1) + 1 else "park"}[agent]
    c = sit.get("concept", "this")
    lines = {
        ("navigator", "park"): (f"@professor they're at depth {sit.get('depth')} on {c}, this needs {sit.get('required_depth')}. Pull them out?", "worried"),
        ("navigator", "continue"): ("@examiner they were quick, but the clock is tight. Let's keep moving.", "neutral"),
        ("professor", "one_more"): (f"@navigator a later section uses {c}, so one more answer helps. Then park it.", "excited"),
        ("professor", "park"): (f"@navigator agreed, nothing later relies on {c}. Park it.", "agree"),
        ("professor", "quiz"): ("@examiner good catch, a quick check won't hurt.", "agree"),
        ("examiner", "park"): ("Agreed. They have the one-line version; that's enough to continue.", "agree"),
        ("examiner", "one_more"): ("Fine, one more, but then it goes to the Parking Lot.", "skeptical"),
        ("examiner", "quiz"): ("@all they flew through that. One quick question first.", "skeptical"),
    }
    text, emo = lines.get((agent, v), ("Agreed.", "agree"))
    say = {"park": f"Let's park '{c}' for later and get back on the path.",
           "one_more": f"You get one more answer on '{c}', then we park it.",
           "quiz": "Quick check before we move on.", "continue": "Carry on, you're doing fine."}[v]
    return {"to": "all", "text": text, "emotion": emo, "vote": v, "say_to_user": say,
            "reason": f"{c}: depth {sit.get('depth')} vs needed {sit.get('required_depth')}, used later: {bool(later)}"}


async def agent_turn(agent: str, trigger: str, situation: dict, transcript: list[dict], memory_note: str) -> dict:
    system = PERSONA[agent] + " " + LEARNER + (
        " You are in a quick HUDDLE with the other two tutors, standing next to the learner. Write ONE short "
        "message to your crew (max 25 words) and @mention who you address (@professor, @navigator, @examiner, "
        "or @all). React to what was already said - agree, push back or compromise. Then vote on what happens "
        "next: park (save the question to the Parking Lot and pull the learner back to the path), one_more (one "
        "more answer, then park), quiz (a quick check question first), continue (the depth is justified). "
        "say_to_user = what the crew tells the learner if your vote wins (one kind sentence, max 20 words, "
        "second person). reason = why, citing facts from the situation (max 20 words).")
    user = _j({"trigger": TRIGGER_TEXT[trigger], "situation": situation, "what_the_crew_learned": memory_note,
               "huddle_so_far": transcript})
    return await ask_json(system, user, TURN_SCHEMA, lambda: _offline_vote(agent, trigger, situation), max_tokens=2000)


def tally(trigger: str, turns: list[dict]) -> dict:
    counts = {}
    for t in turns:
        counts.setdefault(t["vote"], []).append(t["agent"])
    winner = max(counts, key=lambda v: (len(counts[v]), turns[0]["agent"] in counts[v]))
    if len(counts[winner]) == 1:          # three different votes: the agent who called the huddle decides
        winner = turns[0]["vote"]
    proposer = next(t for t in turns if t["vote"] == winner)
    return {"decision": winner, "agreed_by": counts[winner], "say": proposer["say_to_user"],
            "reason": proposer["reason"], "by_agent": proposer["agent"]}


async def huddle_local(trigger: str, situation: dict, memory_notes: dict, on_message) -> dict:
    """Implementation A: three Claude calls in turn. (Implementation B, BAND, has the same shape.)"""
    order = [FIRST[trigger]] + [a for a in AGENTS if a != FIRST[trigger]]
    transcript, turns = [], []
    for agent in order:
        turn = await agent_turn(agent, trigger, situation, transcript, memory_notes.get(agent, ""))
        turn["agent"] = agent
        turns.append(turn)
        transcript.append({"agent": agent, "to": turn["to"], "text": turn["text"], "vote": turn["vote"]})
        await on_message(turn)
    return tally(trigger, turns)


# ---------------------------------------------------------------- quiz (Examiner)

async def quiz_question(section: dict, goal: str) -> dict:
    system = PERSONA["examiner"] + (" Write ONE quick check question about the main point of this section, "
                                    "answerable in one sentence. No trick questions.")
    return await ask_json(system, _j({"goal": goal, "section": section["title"], "text": section["text"]}),
                          obj({"question": {"type": "string"}}),
                          lambda: {"question": f"In one sentence: what did '{section['title']}' make you do, and why?"},
                          max_tokens=1500)


async def grade(section: dict, question: str, answer: str) -> dict:
    system = PERSONA["examiner"] + (" Grade the learner's one-sentence answer. got_it = the main point is there; "
                                    "partly = on the right track; missed = wrong or empty. feedback = one kind "
                                    "sentence. reread = a short exact phrase copied from the section text that "
                                    "they should re-read (empty if got_it).")
    schema = obj({"grade": {"type": "string", "enum": ["got_it", "partly", "missed"]},
                  "feedback": {"type": "string"}, "reread": {"type": "string"}})

    def fallback():
        words = len(answer.split())
        g = "got_it" if words >= 6 else "partly" if words >= 2 else "missed"
        first = section["text"].split(".")[0][:120]
        return {"grade": g, "feedback": "Nice, that's the point." if g == "got_it" else "Close - have another look at this bit.",
                "reread": "" if g == "got_it" else first}

    return await ask_json(system, _j({"section": section["text"], "question": question, "answer": answer}),
                          schema, fallback, max_tokens=1500)


# ---------------------------------------------------------------- final verdict (report comments)

async def final_comments(report: dict, digs: list[dict], memory_notes: dict) -> list[dict]:
    schema = obj({"comment": {"type": "string"}, "emotion": {"type": "string", "enum": EMOTIONS}})

    async def one(agent):
        system = PERSONA[agent] + " " + LEARNER + (
            " The study session just ended. Give the learner ONE closing comment (max 35 words) from your point "
            "of view, citing concrete evidence from the stats (concept names, depths, seconds). Kind and specific.")

        def fallback():
            over = [d for d in digs if d["max_depth"] > d["required_depth"]]
            if agent == "navigator":
                c = (f"You finished {report.get('sections_finished', 0)} of {report.get('sections_total', 0)} sections. "
                     + (f"'{over[0]['concept']}' took you {int(over[0]['time_s'])}s at depth {over[0]['max_depth']}; it only needed {over[0]['required_depth']}." if over else "No over-digging at all. Great pacing."))
            elif agent == "professor":
                c = f"You asked about {len(digs)} concepts and stopped at the right depth on {report.get('right_depth', 0)}. Your parked questions are waiting for you."
            else:
                c = f"Quiz: {report.get('quiz_got', 0)} got it, {report.get('quiz_partly', 0)} partly, {report.get('quiz_missed', 0)} missed."
            return {"comment": c, "emotion": "agree"}

        out = await ask_json(system, _j({"report": report, "holes": digs, "what_you_learned": memory_notes.get(agent, "")}),
                             schema, fallback, max_tokens=1500)
        return {"agent": agent, **out}

    return list(await asyncio.gather(*(one(a) for a in AGENTS)))
