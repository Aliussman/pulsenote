"""Download and convert the PriMock57 dataset into PulseNote format.

Fetches 57 mock primary care consultation dialogues from Hugging Face (sdialog/Primock-57)
and the clinician reference notes from Babylon Health's repository.

Outputs:
    data/encounters.jsonl        57 encounters formatted for PulseNote eval harness
    data/reference_notes.json    Clinician-written reference notes & clinical highlights
"""

import json
import re
import urllib.request
from pathlib import Path

HF_API_URL = "https://huggingface.co/api/datasets/sdialog/Primock-57"
HF_RAW_BASE = "https://huggingface.co/datasets/sdialog/Primock-57/raw/main/"
NOTES_RAW_BASE = "https://raw.githubusercontent.com/babylonhealth/primock57/main/notes/"

CLEAN_TAGS_RE = re.compile(r"</?[A-Za-z0-9_-]+>")


def clean_text(text: str) -> str:
    """Remove markup tags like <UNSURE>...</UNSURE> and normalize whitespace."""
    text = CLEAN_TAGS_RE.sub("", text)
    return " ".join(text.split())


def normalize_speaker(speaker: str) -> str:
    """Normalize speaker name to 'Doctor' or 'Patient' for clinician authority check."""
    s = speaker.strip().lower()
    if any(k in s for k in ("doc", "dr", "clinician", "physician", "gp")):
        return "Doctor"
    return "Patient"


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PulseNote/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(exist_ok=True)

    print("Fetching file index from Hugging Face...")
    meta = fetch_json(HF_API_URL)
    conv_files = sorted(
        [
            s["rfilename"]
            for s in meta.get("siblings", [])
            if s["rfilename"].startswith("data/") and s["rfilename"].endswith("_conversation.json")
        ]
    )

    print(f"Found {len(conv_files)} conversation files to process.")

    encounters = []
    reference_notes = {}

    for idx, rfilename in enumerate(conv_files, start=1):
        filename = Path(rfilename).name
        # e.g., 'day1_consultation01_conversation.json' -> 'day1_consultation01'
        base_id = filename.replace("_conversation.json", "")
        print(f"[{idx}/{len(conv_files)}] Processing {base_id}...")

        # 1. Download dialogue turns
        conv_url = HF_RAW_BASE + rfilename
        try:
            conv_data = fetch_json(conv_url)
        except Exception as e:
            print(f"  Warning: failed to download conversation {base_id}: {e}")
            continue

        raw_turns = conv_data.get("turns", [])
        formatted_turns = []
        turn_counter = 1

        for raw_turn in raw_turns:
            text = clean_text(raw_turn.get("text", ""))
            if not text:
                continue
            speaker = normalize_speaker(raw_turn.get("speaker", "Doctor"))
            formatted_turns.append({"id": turn_counter, "speaker": speaker, "text": text})
            turn_counter += 1

        if not formatted_turns:
            print(f"  Warning: no turns found for {base_id}, skipping.")
            continue

        encounter_rec = {"id": base_id, "turns": formatted_turns}
        encounters.append(encounter_rec)

        # 2. Download corresponding clinician reference note
        note_url = f"{NOTES_RAW_BASE}{base_id}.json"
        try:
            note_data = fetch_json(note_url)
            reference_notes[base_id] = {
                "presenting_complaint": note_data.get("presenting_complaint"),
                "note": note_data.get("note"),
                "highlights": note_data.get("highlights", []),
            }
        except Exception as e:
            print(f"  Note info unavailable for {base_id}: {e}")

    # Write data/encounters.jsonl
    encounters_path = data_dir / "encounters.jsonl"
    with open(encounters_path, "w", encoding="utf-8") as f:
        for enc in encounters:
            f.write(json.dumps(enc) + "\n")
    print(f"\nSaved {len(encounters)} encounters to {encounters_path}")

    # Write data/reference_notes.json
    ref_notes_path = data_dir / "reference_notes.json"
    with open(ref_notes_path, "w", encoding="utf-8") as f:
        json.dump(reference_notes, f, indent=2)
    print(f"Saved {len(reference_notes)} clinician reference notes to {ref_notes_path}")


if __name__ == "__main__":
    main()
