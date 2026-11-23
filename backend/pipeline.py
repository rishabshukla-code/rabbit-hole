"""Runs the Bruin pipelines and reads their tables. Falls back to a tiny local runner
(same asset files, same SQL) if the Bruin CLI is missing or fails, so the demo never dies."""
import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time

import duckdb

from config import BRUIN_BIN, BRUIN_DIR, DB, EVENTS, ROOT, WORK

log = logging.getLogger("pipeline")
EVENT_KEYS = ["session_id", "ts", "type", "section_idx", "concept", "category", "depth", "required_depth",
              "is_followup", "trigger", "decision", "agreed_by", "grade", "duration_s", "count", "text", "agent", "goal"]


def log_event(session_id: str, type_: str, **fields):
    row = {k: None for k in EVENT_KEYS}
    row.update(session_id=session_id, ts=time.time(), type=type_)
    row.update({k: v for k, v in fields.items() if k in row})
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def query(sql: str, params=None) -> list[dict]:
    if not DB.exists():
        return []
    try:
        con = duckdb.connect(str(DB), read_only=True)
        try:
            cur = con.execute(sql, params or [])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            con.close()
    except duckdb.Error as e:
        log.info("query failed (%s): %s", e.__class__.__name__, e)
        return []


def _bruin(pipeline: str) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run([BRUIN_BIN, "run", str(BRUIN_DIR / pipeline)], cwd=ROOT, env=os.environ.copy(),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        out = p.stdout + p.stderr
        assets = re.search(r"Assets executed\s+(\d+) succeeded", out)
        checks = re.search(r"Quality checks\s+(\d+) succeeded", out)
        ok = p.returncode == 0 and assets is not None
        if not ok:
            log.warning("bruin run %s failed:\n%s", pipeline, out[-2000:])
        return {"ok": ok, "runner": "bruin", "assets": int(assets.group(1)) if assets else 0,
                "checks": int(checks.group(1)) if checks else 0, "seconds": round(time.time() - t0, 1)}
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("bruin not runnable: %s", e)
        return {"ok": False, "runner": "bruin", "assets": 0, "checks": 0, "seconds": round(time.time() - t0, 1)}


def _header(path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"@bruin(.*?)@bruin", text, re.S)
    head = m.group(1) if m else ""
    name = re.search(r"^name:\s*(\S+)", head, re.M).group(1)
    dm = re.search(r"depends:\s*\n((?:[ \t]+-[ \t]+\S+[ \t]*\n)+)", head)
    deps = re.findall(r"-\s+(\S+)", dm.group(1)) if dm else []
    body = text[m.end():].lstrip(" */\n") if m and path.suffix == ".sql" else ""
    return {"name": name, "deps": deps, "path": path, "body": body}


def _local_run(pipeline: str) -> dict:
    """Same assets, run without the Bruin CLI: Python assets as scripts, SQL as CREATE TABLE AS."""
    t0 = time.time()
    assets = {a["name"]: a for a in (_header(p) for p in (BRUIN_DIR / pipeline / "assets").iterdir()
                                     if p.suffix in (".py", ".sql"))}
    done, order = set(), []
    while len(order) < len(assets):
        for n, a in assets.items():
            if n not in done and all(d in done or d not in assets for d in a["deps"]):
                done.add(n)
                order.append(a)
    for a in order:
        if a["path"].suffix == ".py":
            subprocess.run([sys.executable, str(a["path"])], cwd=ROOT, check=True, timeout=120)
        else:
            con = duckdb.connect(str(DB))
            try:
                schema = a["name"].split(".")[0]
                con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                con.execute(f"CREATE OR REPLACE TABLE {a['name']} AS {a['body']}")
            finally:
                con.close()
    return {"ok": True, "runner": "local", "assets": len(order), "checks": 0, "seconds": round(time.time() - t0, 1)}


def run_pipeline(pipeline: str) -> dict:
    res = _bruin(pipeline)
    if not res["ok"]:
        try:
            res = _local_run(pipeline)
        except Exception as e:  # last line of defence
            log.error("local runner failed too: %s", e)
    return res


async def prepare_material(session_id: str, material: str, goal: str) -> tuple[dict, list, list]:
    """Bruin material pipeline -> (run info, sections, concepts)."""
    WORK.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{goal}\n{material}".encode()).hexdigest()[:16]
    cache = WORK / "material_hash.txt"
    cached = cache.exists() and cache.read_text() == digest and os.getenv("RH_CACHE", "1") == "1"
    if cached and query("SELECT 1 FROM core.concepts LIMIT 1"):
        run = {"ok": True, "runner": "cache", "assets": 4, "checks": 0, "seconds": 0}
    else:
        (WORK / "material.md").write_text(material, encoding="utf-8")
        (WORK / "meta.json").write_text(json.dumps({"session_id": session_id, "goal": goal}), encoding="utf-8")
        run = await asyncio.to_thread(run_pipeline, "material")
        cache.write_text(digest)
    sections = query("SELECT idx, title, text, word_count, is_key FROM raw.material_sections ORDER BY idx")
    concepts = query("SELECT concept_id, name, aliases, section_idx, category, required_depth, used_later, depth1_answer "
                     "FROM core.concepts ORDER BY section_idx")
    return run, sections, concepts


def load_memory() -> dict:
    """What the crew remembers from earlier sessions (built by the analytics pipeline)."""
    policy = {r["category"]: r for r in query("SELECT * FROM marts.crew_policy")}
    scores = {r["agent"]: r for r in query("SELECT * FROM marts.agent_scores")}
    profile = query("SELECT * FROM marts.learner_profile ORDER BY over_dig_rate DESC")
    sessions = query("SELECT count(*) AS n FROM marts.session_report")
    return {"policy": policy, "scores": scores, "profile": profile, "sessions": sessions[0]["n"] if sessions else 0}


async def analyze_session(session_id: str) -> tuple[dict, dict, list]:
    run = await asyncio.to_thread(run_pipeline, "analytics")
    report = query("SELECT * FROM marts.session_report WHERE session_id = ?", [session_id])
    digs = query("SELECT * FROM staging.concept_digs WHERE session_id = ? ORDER BY section_idx", [session_id])
    return run, (report[0] if report else {}), digs
