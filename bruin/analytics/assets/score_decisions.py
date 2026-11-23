"""@bruin
name: ingest.decision_scores
image: python:3.12
description: >
  PYTHON SCORING. Gives every past crew decision a reward from what happened next
  (did the learner override it? pass the quiz? finish the material?) and credits it
  to the agents who voted for it. marts.crew_policy turns these scores into the
  settings each agent loads at the next session.
@bruin"""
import json
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data"


def reward(decision, overridden, grade, coverage):
    if decision == "park":
        if overridden or grade == "missed":
            return -1
        return 0 if grade == "partly" else 1
    if decision in ("one_more", "continue"):
        if coverage < 0.8:
            return -1      # the extra depth cost the finish
        return 1 if grade in (None, "got_it") else 0
    if decision == "quiz":
        return 1 if grade in ("partly", "missed") else 0   # it caught a real gap
    return 0


def main():
    path = DATA / "events.jsonl"
    events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []
    by_session = defaultdict(list)
    for e in events:
        by_session[e["session_id"]].append(e)
    rows = []
    for sid, evs in by_session.items():
        total = max([e.get("count") or 0 for e in evs if e["type"] == "session_start"] or [0])
        finished = {e.get("section_idx") for e in evs if e["type"] == "section_finish"}
        coverage = len(finished) / total if total else 0.0
        for h in evs:
            if h["type"] != "huddle" or not h.get("decision") or h.get("trigger") == "final":
                continue
            later = [e for e in evs if e["ts"] > h["ts"]]
            overridden = any(e["type"] == "override" and e.get("concept") == h.get("concept") for e in later)
            grades = [e.get("grade") for e in later if e["type"] == "quiz_graded" and e.get("section_idx") == h.get("section_idx")]
            grade = grades[0] if grades else None
            r = reward(h["decision"], overridden, grade, coverage)
            for agent in (h.get("agreed_by") or "").split(","):
                if agent:
                    rows.append({"session_id": sid, "ts": h["ts"], "agent": agent, "trigger": h.get("trigger"),
                                 "decision": h["decision"], "concept": h.get("concept"), "category": h.get("category"),
                                 "reason": h.get("text") or "", "overridden": overridden, "quiz_grade": grade,
                                 "coverage": round(coverage, 2), "reward": r})
    (DATA / "work").mkdir(parents=True, exist_ok=True)
    (DATA / "work" / "decision_scores.json").write_text(json.dumps(rows), encoding="utf-8")
    print(f"scored {len(rows)} agent decisions across {len(by_session)} sessions")


main()
