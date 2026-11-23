# 🕳️ Rabbit Hole

**A crew of three AI tutors that pulls you out of rabbit holes, so you finish what matters and save your curiosity for later.**

*Multiplayer AI Hackathon · Track 3: Grow with Agents*

---

## The problem

The tutorial says *"we use a virtual environment for this project."* You wonder what a virtual environment is. Then how it works. Then why it was invented. An hour later you know how venvs isolate packages internally, and you still haven't finished the tutorial. For this material, one sentence would have been enough.

Many people, especially people with ADHD, don't fail at studying because they lack interest. **Their curiosity digs deeper than the task needs.** People without this struggle stop at the surface automatically. Rabbit Hole gives you a crew that knows how deep is deep enough, and **parks the rest instead of deleting it**.

## How it works

1. **Paste anything you're studying** and pick a goal: *Get the gist*, *Do the task* or *Exam prep*.
2. **A Bruin pipeline reads it.** Claude finds every concept a curious reader might stop on and decides **how deep you need it for your goal** (1 = what it is, 2 = how to use it, 3 = how it works inside). Bruin's quality checks validate that AI-generated data before the crew uses it.
3. **Walk the 3D path.** Each section is a stepping stone. When something is unfamiliar, **ask the crew instead of opening a new tab**.
4. **You dig your own holes.** A question opens a hole next to your stone, and every follow-up digs one level deeper. The world gets darker, and the rim glows red when you pass the depth the material needs.
5. **The crew huddles.** Three agents with conflicting goals walk over, argue with @mentions in a **BAND room**, and **vote**: park it, one more answer, quiz first, or keep digging. Every message, vote and reason appears in the Crew Log and is spoken in each agent's voice.
6. **Report.** You see sections covered, how often you stopped at the right depth, each hole (how deep you went vs. how deep you needed), quiz results, crew comments citing evidence, and your **Parking Lot**, where you can explore freely now that the session is over.
7. **The crew trains on every session.** Bruin scores every decision by what happened next and tunes the crew for your next session.

## The crew

| Agent | Goal (they pull against each other) | Speaks first when… |
|---|---|---|
| 👩‍🏫 **Professor** | You **understand** what the material needs | Answering every question; defends depth that an upcoming section relies on |
| 🧭 **Navigator** | You **finish** in your time budget | You dig past the needed depth, or stay in one hole too long |
| 📝 **Examiner** | You can **prove** you got it | You skim a section; key sections; before granting more depth |

Each agent is a **separate Claude call with its own system prompt**, a separate **BAND agent with its own identity and API key**, and its own 3D character, color and voice. **Code decides when** a huddle happens (fixed triggers: over the needed depth, too long in one hole, skimmed a section). **The agents decide what happens.** The outcome is the majority vote, and if all three disagree, the agent who called the huddle decides.

## Sponsor tools

### Bruin: the crew's memory and its trainer
Two Bruin pipelines (`bruin/`), run by the backend with `bruin run`, on DuckDB:

```
material pipeline (on Start)
  ingest.sections (Python) ──▶ raw.material_sections (SQL, checks)
  ingest.concepts (Python: Claude extracts concepts + needed depth) ──▶ core.concepts (SQL)
        └─ checks: accepted_values on category and depth, unique ids,
           custom: every concept points at a real section, one-line answers stay short

analytics pipeline (on End)
  staging.events (SQL: the app's event log, typed + validated)
    ├─▶ staging.concept_digs ──▶ marts.session_report      (the Report screen)
    │                        └─▶ marts.learner_profile     (over-dig rate per concept category)
    └─▶ ingest.decision_scores (PYTHON SCORING: a reward for every crew decision)
          └─▶ raw.decision_scores ──▶ marts.agent_scores   (how often each agent was right, best examples)
                                 └─▶ marts.crew_policy     (TRAINING OUTPUT: per-category depth tolerance
                                                            and timing, loaded by the agents next session)
```

**How decisions are scored** (`bruin/analytics/assets/score_decisions.py`): a *park* earns +1 if you didn't override it and passed that section's quiz, and −1 if you overrode it or failed the quiz. *One more* and *continue* earn −1 if the extra depth cost you the finish. A *quiz* earns +1 when it caught a real gap. `marts.crew_policy` turns those rewards into the settings the crew runs with: for example *"Crew learned to allow 1 extra level on tooling concepts"* after you overrode its parks, or *"steps in sooner"* where you over-dig. Each agent's best-scored past decisions go into its prompt as examples.

Quality checks guard Claude's output: **the crew never acts on unchecked AI-generated data.**

### BAND: where the crew talks
Every study session creates a BAND room with the three agents and their human owner. In a huddle, each agent **reads the room history from BAND**, thinks, and **posts as itself with real @mentions** of the others, and the decision is posted too. The room can be watched live in the BAND app. If BAND is unreachable, the huddle finishes locally, so a demo never breaks. Code: `backend/band_room.py`.

### AdaL
The demo video was made with AdaL Desktop.

## Architecture

```
Browser (Vite + React + React Three Fiber)          Python backend (FastAPI)
  3D world · reading · ask box · crew log    ◀──WS──▶   session.py   triggers, holes, decisions, quizzes
  browser voices (one per agent) + mic                crew.py      the 3 agents (Claude, structured JSON)
                                                      band_room.py huddles in a BAND room
                                                      pipeline.py  runs Bruin, reads DuckDB
                                                      events ──▶ data/events.jsonl ──▶ Bruin
```

- **LLM:** Claude Opus 5.5 (`claude-opus-5-5`, low effort, structured outputs). Every call has an offline fallback, so the app also runs without an API key.
- **3D:** React Three Fiber + drei. Characters glide to clicked stones, sink into holes, huddle, face the speaker, bounce while talking and show emotion icons. Optional animated GLB characters load from `frontend/public/characters/`.

## Run it

Requirements: Python 3.11+, Node 20+, the [Bruin CLI](https://getbruin.com/docs), and an Anthropic API key. BAND agents are optional.

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt      # macOS/Linux: .venv/bin/pip
cd frontend && npm install && cd ..
```

Create `backend/.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

Optional BAND: register three remote agents (Professor, Navigator, Examiner) at app.band.ai, then create `backend/agent_config.yaml`:
```yaml
professor: { agent_id: "...", api_key: "..." }
navigator: { agent_id: "...", api_key: "..." }
examiner:  { agent_id: "...", api_key: "..." }
```
Check it with `python backend/band_check.py`.

Start both servers, then open http://localhost:5173 in Chrome (Chrome is needed for the voices and the mic):
```bash
cd backend && ../.venv/Scripts/python -m uvicorn app:app --port 8000
cd frontend && npm run dev
```

Tests (backend running): `python backend/smoke_test.py` (short session) and `python backend/e2e_test.py` (every trigger, override, report, explore, memory).

## What's next
- **The same crew for any task that feels impossible.** Cooking dinner becomes a path of tiny steps, with a Head Chef, a Sous-chef who gives one small step at a time, and a Timer.
- PDF upload, and a "body double" mode for your real to-do list.
