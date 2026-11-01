"""Make a worksheet for writing gold key facts, and an empty skeleton file to fill in.

Write the facts from the transcript and the clinician reference note, NOT from model output,
so the gold standard cannot drift toward whatever a model happened to write. Do this before
you look at any model output for these encounters.

Usage (from the project root):
    python scripts/draft_key_facts.py --data data/encounters_eval.jsonl --notes data/reference_notes.json

Outputs:
    data/key_facts_worksheet.md        numbered transcripts plus reference notes, to read from
    data/key_facts_eval.draft.jsonl    {"id": ..., "facts": []} per encounter, to fill in

Then check your work with:  python -m eval.lint_key_facts --facts data/key_facts_eval.jsonl --data data/encounters_eval.jsonl
"""

import argparse
import json
from pathlib import Path


def render_note(note) -> str:
    if isinstance(note, str):
        return note
    return json.dumps(note, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/encounters_eval.jsonl")
    parser.add_argument("--notes", default="data/reference_notes.json")
    parser.add_argument("--worksheet", default="data/key_facts_worksheet.md")
    parser.add_argument("--draft", default="data/key_facts_eval.draft.jsonl")
    args = parser.parse_args()

    with open(args.data) as f:
        encounters = [json.loads(line) for line in f if line.strip()]
    notes = json.loads(Path(args.notes).read_text()) if Path(args.notes).exists() else {}

    lines = ["# Key fact worksheet", "", "Write 5 to 10 atomic facts per encounter. One fact, one idea.", ""]
    for enc in encounters:
        lines += [f"## {enc['id']}", "", "### Transcript", ""]
        lines += [f"[T{t['id']}] {t['speaker']}: {t['text']}" for t in enc["turns"]]
        note = notes.get(enc["id"]) if isinstance(notes, dict) else None
        lines += ["", "### Reference note", "", render_note(note) if note else "(no reference note found)", ""]
    Path(args.worksheet).write_text("\n".join(lines))

    with open(args.draft, "w") as f:
        for enc in encounters:
            f.write(json.dumps({"id": enc["id"], "facts": []}) + "\n")
    print(f"wrote {args.worksheet} and {args.draft} for {len(encounters)} encounters")


if __name__ == "__main__":
    main()
