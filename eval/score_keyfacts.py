"""Usage: python -m eval.score_keyfacts --facts data/key_facts.jsonl --rows results/per_sentence.jsonl"""

import argparse
import json
from pathlib import Path

from eval.keyfacts import compute_recall, load_key_facts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", required=True)
    parser.add_argument("--rows", default="results/per_sentence.jsonl")
    parser.add_argument("--out", default="results/keyfact_recall.json")
    args = parser.parse_args()

    facts = load_key_facts(args.facts)
    with open(args.rows) as f:
        rows = [json.loads(line) for line in f if line.strip()]

    result = compute_recall(rows, facts)
    Path(args.out).write_text(json.dumps(result, indent=2))

    print("variant               recalled / total   recall   encounters")
    for variant, s in result.items():
        print(f"{variant:<21} {s['recalled']:>4} / {s['total']:<9} {s['recall']:.1%}    {s['encounters_scored']}")
    print("\nby category")
    categories = sorted({c for s in result.values() for c in s["by_category"]})
    for cat in categories:
        parts = []
        for variant, s in result.items():
            c = s["by_category"].get(cat)
            parts.append(f"{variant} {c['recalled']}/{c['total']}" if c else f"{variant} -")
        print(f"  {cat:<12} " + "   ".join(parts))


if __name__ == "__main__":
    main()
