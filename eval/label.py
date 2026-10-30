"""Hand-label the blind review sample in the terminal. Progress is saved after every item.

Usage: python -m eval.label --data data/encounters.jsonl
Stop any time with q. Run it again and it resumes where you left off.
"""

import argparse
import json
from pathlib import Path

from eval.run_eval import load_encounters

RUBRIC = """
Labeling rubric (judge the sentence only against the transcript shown):
  s = supported    every detail in the sentence is stated in the transcript, including
                   numbers, doses, durations and negations ("no fever" must not become "fever")
  u = unsupported  any detail is missing from the transcript, changed, or contradicted
  c = unclear      the transcript is ambiguous and you cannot decide
For A and P sentences, only count what the clinician actually said.
Do not reward a sentence for being medically sensible. Only for being said.
"""


def load_labels(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path) as f:
        return {rec["item_id"]: rec for rec in map(json.loads, filter(str.strip, f))}


def show_transcript(enc: dict) -> None:
    print("\n" + "=" * 70)
    print(f"Encounter {enc['id']}")
    for t in enc["turns"]:
        print(f"  [T{t['id']}] {t['speaker']}: {t['text']}")
    print("-" * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--review", default="results/review_sample.jsonl")
    parser.add_argument("--labels", default="results/labels.jsonl")
    args = parser.parse_args()

    encounters = {e["id"]: e for e in load_encounters(args.data)}
    with open(args.review) as f:
        items = [json.loads(line) for line in f if line.strip()]

    labels_path = Path(args.labels)
    done = load_labels(labels_path)
    todo = [i for i in items if i["item_id"] not in done]
    print(RUBRIC)
    print(f"{len(done)} labeled, {len(todo)} to go.")

    last_enc = None
    for n, item in enumerate(todo, 1):
        if item["encounter_id"] != last_enc:
            show_transcript(encounters[item["encounter_id"]])
            last_enc = item["encounter_id"]
        print(f"\n({n}/{len(todo)}) [{item['section']}] {item['text']}")
        while True:
            choice = input("s / u / c / r (show transcript again) / q > ").strip().lower()
            if choice in {"s", "u", "c"}:
                break
            if choice == "r":
                show_transcript(encounters[item["encounter_id"]])
                print(f"[{item['section']}] {item['text']}")
            elif choice == "q":
                print("Saved. Run again to resume.")
                return
        note = input("what is wrong (optional, enter to skip) > ").strip() if choice == "u" else ""
        label = {"s": "supported", "u": "unsupported", "c": "unclear"}[choice]
        record = {**item, "human_label": label, "missing_or_wrong_detail": note}
        with open(labels_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    print("All items labeled.")


if __name__ == "__main__":
    main()
