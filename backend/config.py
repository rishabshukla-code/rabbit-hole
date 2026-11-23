"""Paths, settings and environment for the Rabbit Hole backend."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATA = ROOT / "data"
WORK = DATA / "work"          # files the Bruin Python assets read and write
EVENTS = DATA / "events.jsonl"
DB = DATA / "rabbit.db"
BRUIN_DIR = ROOT / "bruin"
CONTENT = ROOT / "content"
for d in (DATA, WORK):
    d.mkdir(parents=True, exist_ok=True)

BRUIN_BIN = os.getenv("BRUIN_BIN") or str(Path.home() / ".local" / "bin" / ("bruin.exe" if os.name == "nt" else "bruin"))

MODEL = os.getenv("RH_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("RH_EFFORT", "low")
OFFLINE = os.getenv("RH_OFFLINE", "") == "1" or not os.getenv("ANTHROPIC_API_KEY")

# Demo-scaled timings (seconds). Section 4 of SPEC.md.
HOLE_LIMIT_S = float(os.getenv("RH_HOLE_LIMIT", "30"))
HUDDLE_COOLDOWN_S = float(os.getenv("RH_COOLDOWN", "20"))
SKIM_S_PER_100_WORDS = float(os.getenv("RH_SKIM", "10"))
