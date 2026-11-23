"""@bruin
name: ingest.sections
image: python:3.12
description: Splits the pasted study material into sections (one stepping stone each).
@bruin"""
import json
import re
from pathlib import Path

WORK = Path(__file__).resolve().parents[3] / "data" / "work"


def split_sections(text: str) -> list[dict]:
    parts = re.split(r"^##\s+", text, flags=re.M)
    sections = []
    if len(parts) > 1:
        for p in parts[1:]:
            title, _, body = p.partition("\n")
            sections.append({"title": re.sub(r"^\d+[.)]\s*", "", title.strip()), "text": body.strip()})
    else:  # no headings: group paragraphs into ~150-word chunks
        chunk, words = [], 0
        for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
            chunk.append(para)
            words += len(para.split())
            if words >= 150:
                sections.append({"title": f"Part {len(sections) + 1}", "text": "\n\n".join(chunk)})
                chunk, words = [], 0
        if chunk:
            sections.append({"title": f"Part {len(sections) + 1}", "text": "\n\n".join(chunk)})
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
