"""@bruin
name: ingest.sections
image: python:3.12
description: Splits the pasted study material into sections (one stepping stone each).
@bruin"""
import json
import re
from pathlib import Path

WORK = Path(__file__).resolve().parents[3] / "data" / "work"


JUNK = {"copy page", "copy", "share", "edit this page", "on this page", "table of contents"}
MAX_SECTIONS = 8


def _is_heading(line: str, prev: str, nxt: str) -> bool:
    """A plain-text heading (web pages pasted as text lose their # marks): a short line on its own,
    no sentence punctuation, after a finished sentence (not inside a list), followed by body text."""
    if not line or len(line) > 70 or "\t" in line or ":" in line or len(line.split()) > 9:
        return False
    if line[0] in "-*•[(/0123456789" or line.endswith((".", ",", ";", "?", "!", ")", "]")):
        return False
    if prev and not (prev.endswith((".", "!", "?", "”", '"')) or "\t" in prev):
        return False   # previous line is a list item, a table row or another heading
    return len(nxt) > len(line) + 15


def _blocks(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n")
    level = "#{2,3}" if re.search(r"^#{2,3}\s+\S", text, re.M) else "#"   # a lone "# Title" is not a section
    if re.search(rf"^{level}\s+\S", text, re.M):                    # markdown headings
        text = re.sub(r"^#\s+.*$", "", text, flags=re.M) if level != "#" else text
        parts = re.split(rf"^{level}\s+", text, flags=re.M)
        lead = parts[0].strip()
        out = [{"title": "Introduction", "text": lead}] if len(lead.split()) > 25 else []
        for p in parts[1:]:
            title, _, body = p.partition("\n")
            out.append({"title": title.strip(), "text": body.strip()})
        return out
    lines = [l.strip() for l in text.split("\n")]
    lines = [l for l in lines if l.lower() not in JUNK]
    out, cur = [], {"title": "Introduction", "text": []}
    for i, line in enumerate(lines):
        nxt = next((l for l in lines[i + 1:] if l), "")
        prev = next((l for l in reversed(lines[:i]) if l), "")
        if _is_heading(line, prev, nxt):
            if cur["text"] or out:
                out.append(cur)
            cur = {"title": line, "text": []}
        elif line:
            cur["text"].append(line)
    out.append(cur)
    out = [{"title": b["title"], "text": "\n".join(b["text"])} for b in out]
    if len(out) <= 1:                                              # no headings at all: ~200-word chunks
        words, chunks, chunk = 0, [], []
        sentences = [s for l in lines if l for s in re.split(r"(?<=[.!?])\s+", l) if s]
        for line in sentences:
            chunk.append(line)
            words += len(line.split())
            if words >= 200:
                chunks.append(chunk)
                chunk, words = [], 0
        if chunk:
            chunks.append(chunk)
        out = [{"title": c[0][:50].rstrip(" ,.:;") + ("..." if len(c[0]) > 50 else ""), "text": " ".join(c)} for c in chunks]
    return out


def split_sections(text: str) -> list[dict]:
    blocks = [b for b in _blocks(text) if b["text"].strip() or b["title"].strip()]
    total = sum(len(b["text"].split()) for b in blocks) or 1
    # keep the author's sections; only merge when there are too many stones, or a section is tiny
    target = total / MAX_SECTIONS if len(blocks) > MAX_SECTIONS else 40
    sections, cur = [], None
    for b in blocks:                                               # merge small neighbours into one stone
        if cur is None:
            cur = {"title": b["title"], "text": b["text"]}
        else:
            cur["text"] = (cur["text"] + "\n\n" + (b["title"] + "\n" if b["title"] else "") + b["text"]).strip()
        if len(cur["text"].split()) >= target:
            sections.append(cur)
            cur = None
    if cur and cur["text"].strip():
        if sections and len(cur["text"].split()) < target / 3:
            sections[-1]["text"] += "\n\n" + cur["title"] + "\n" + cur["text"]
        else:
            sections.append(cur)
    for s in sections:
        s["title"] = re.sub(r"^\d+[.)]\s*", "", s["title"]).strip() or "Part"
        s["text"] = s["text"].strip()
    for i, s in enumerate(sections):
        s["idx"] = i
        s["word_count"] = len(s["text"].split())
    # the two longest sections are "key": the Examiner checks them on finish
    for s in sorted(sections, key=lambda s: -s["word_count"])[:2]:
        s["is_key"] = True
    for s in sections:
        s.setdefault("is_key", False)
    return sections


def main():
    text = (WORK / "material.md").read_text(encoding="utf-8")
    meta = json.loads((WORK / "meta.json").read_text(encoding="utf-8"))
    rows = [{"session_id": meta["session_id"], **s} for s in split_sections(text)]
    (WORK / "sections.json").write_text(json.dumps(rows), encoding="utf-8")
    print(f"wrote {len(rows)} sections")


main()
