"""@bruin
name: ingest.concepts
image: python:3.12
description: >
  Claude reads every section and lists the concepts it mentions, with a category and the
  depth (1-3) a learner needs FOR THE CHOSEN GOAL, plus a ready one-line answer.
  Quality checks downstream (core.concepts) guard this AI-generated data.
depends:
  - ingest.sections
@bruin"""
import json
import os
from pathlib import Path

WORK = Path(__file__).resolve().parents[3] / "data" / "work"
MODEL = os.getenv("RH_MODEL", "claude-opus-5-5")

GOAL_RULES = {
    "gist": "Goal 'Get the gist': almost everything is depth 1. Only the single main idea of a section may be 2.",
    "task": "Goal 'Do the task': depth 1 if only mentioned in passing; depth 2 if the reader must actually use it to finish the task; 3 almost never.",
    "exam": "Goal 'Exam prep': depth 2 for anything used; depth 3 only for the main ideas the text explains; passing mentions stay 1.",
}

SCHEMA = {
    "type": "object",
    "properties": {"concepts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "section_idx": {"type": "integer"},
            "category": {"type": "string", "enum": ["tooling", "theory", "history", "math", "other"]},
            "required_depth": {"type": "integer", "enum": [1, 2, 3]},
            "used_later": {"type": "boolean"},
            "depth1_answer": {"type": "string"},
        },
        "required": ["name", "aliases", "section_idx", "category", "required_depth", "used_later", "depth1_answer"],
        "additionalProperties": False,
    }}},
    "required": ["concepts"],
    "additionalProperties": False,
}

# Offline fallback for the demo chapter (used if there is no API key or the call fails).
FALLBACK = [
    ("virtual environment", ["venv", ".venv", "virtualenv"], 0, "tooling", 1, True, "A separate folder of Python packages just for this project, so projects don't clash."),
    ("git", ["git init", "version control"], 0, "tooling", 1, False, "A tool that tracks every change to your project's files."),
    ("flask", ["web framework"], 1, "tooling", 2, True, "A small Python library that turns functions into web pages."),
    ("pip", ["pip install", "pip freeze"], 1, "tooling", 2, True, "Python's package installer: it downloads libraries into your environment."),
    ("requirements.txt", ["requirements"], 1, "tooling", 1, False, "A file listing the exact packages a project needs."),
    ("docker", ["container", "containers"], 1, "tooling", 1, False, "A way to ship an app with everything it needs inside a sealed box."),
    ("decorator", ["@app.route"], 2, "theory", 1, False, "A line starting with @ that wraps the function below it."),
    ("api", ["json"], 2, "theory", 1, False, "Routes that return data instead of pages, for other programs to use."),
    ("port", ["5000"], 3, "theory", 1, False, "A door number on your computer where an app listens."),
    ("environment variables", ["env vars", ".env", "os.environ"], 4, "tooling", 2, False, "Values your operating system holds that your app reads when it starts."),
]


def fallback(sections):
    n = len(sections)
    out = []
    for name, aliases, idx, cat, depth, later, ans in FALLBACK:
        text = " ".join(s["text"].lower() for s in sections)
        if name in text or any(a.lower() in text for a in aliases):
            out.append({"name": name, "aliases": aliases, "section_idx": min(idx, n - 1), "category": cat,
                        "required_depth": depth, "used_later": later, "depth1_answer": ans})
    return out or [{"name": "main idea", "aliases": [], "section_idx": 0, "category": "other",
                    "required_depth": 1, "used_later": False, "depth1_answer": "The central point of this text."}]


def extract(sections, goal):
    if not os.getenv("ANTHROPIC_API_KEY") or os.getenv("RH_OFFLINE") == "1":
        return fallback(sections), "offline"
    import anthropic
    client = anthropic.Anthropic(timeout=60.0, max_retries=1)
    material = "\n\n".join(f"[section {s['idx']}] {s['title']}\n{s['text']}" for s in sections)
    system = (
        "You prepare study material for a learner who tends to dig far deeper into side concepts than the "
        "task needs. List every concept, tool or term a curious reader might stop and look up (aim for 6-12). "
        "For each: the section where it first appears, a category, and required_depth = how deep the reader "
        "must understand it FOR THIS GOAL: 1 = what it is (one line), 2 = how to use it, 3 = how it works "
        "inside / why / history. " + GOAL_RULES.get(goal, GOAL_RULES["task"]) +
        " used_later = true if a LATER section relies on it. depth1_answer = one plain sentence, max 25 words. "
        "Use short lowercase names; aliases = other ways the text or a reader might say it."
    )
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=8000, system=system,
            messages=[{"role": "user", "content": material}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)["concepts"], "llm"
    except Exception as e:  # any failure: keep the demo alive with the fallback list
        print(f"concept extraction failed ({type(e).__name__}: {e}); using fallback")
        return fallback(sections), "offline"


def main():
    sections = json.loads((WORK / "sections.json").read_text(encoding="utf-8"))
    meta = json.loads((WORK / "meta.json").read_text(encoding="utf-8"))
    concepts, src = extract(sections, meta.get("goal", "task"))
    rows = []
    for i, c in enumerate(concepts):
        rows.append({
            "session_id": meta["session_id"], "concept_id": f"c{i}", "name": c["name"].strip().lower(),
            "aliases": "|".join(a.strip().lower() for a in c["aliases"]), "section_idx": c["section_idx"],
            "category": c["category"], "required_depth": c["required_depth"], "used_later": c["used_later"],
            "depth1_answer": c["depth1_answer"].strip(), "source": src,
        })
    (WORK / "concepts.json").write_text(json.dumps(rows), encoding="utf-8")
    print(f"wrote {len(rows)} concepts ({src})")


main()
