"""Run baseline and grounded pipelines over a set of encounters and score them.

Usage (from the project root):
    export PULSENOTE_MODEL=<model name>
    python -m eval.run_eval --data data/encounters.jsonl --n 10 --out results/

Input format, one JSON object per line:
    {"id": "enc_001", "turns": [{"id": 1, "speaker": "Doctor", "text": "..."}, ...]}
"""

import argparse
import json
import random
import time
from pathlib import Path

from eval.metrics import format_table, summarize
from src.baseline import generate_baseline
from src.pipeline import LLMCall, generate_note
from src.posthoc import post_hoc_check
from src.schemas import Turn


def load_encounters(path: str, n: int | None = None, seed: int = 0) -> list[dict]:
    with open(path) as f:
        encounters = [json.loads(line) for line in f if line.strip()]
    if n is not None and n < len(encounters):
        encounters = random.Random(seed).sample(encounters, n)
    return encounters


def make_row(system: str, check: str, enc_id: str, sentence, reasons: list[str]) -> dict:
    return {
        "system": system,
        "check": check,
        "encounter_id": enc_id,
        "section": sentence.section,
        "text": sentence.text,
        "support": [s.model_dump() for s in sentence.support],
        "flagged": bool(reasons),
        "reasons": reasons,
    }


def run(encounters: list[dict], call_llm: LLMCall):
    rows: list[dict] = []
    latencies: dict[str, list[float]] = {"baseline": [], "grounded": []}
    failures = {"baseline": 0, "grounded": 0}

    for enc in encounters:
        turns = [Turn(**t) for t in enc["turns"]]

        try:
            start = time.perf_counter()
            raw = generate_baseline(turns, call_llm)
            latencies["baseline"].append(time.perf_counter() - start)
        except Exception as e:
            failures["baseline"] += 1
            print(f"[baseline] {enc['id']} failed: {e}")
        else:
            for s in raw.sentences:
                rows.append(make_row("baseline", "posthoc", enc["id"], s, post_hoc_check(s.text, s.section, turns)))

        try:
            start = time.perf_counter()
            note = generate_note(turns, call_llm)
            latencies["grounded"].append(time.perf_counter() - start)
        except Exception as e:
            failures["grounded"] += 1
            print(f"[grounded] {enc['id']} failed: {e}")
        else:
            for s in note.sentences:
                rows.append(make_row("grounded", "citation", enc["id"], s, s.flag_reasons))
                rows.append(make_row("grounded", "posthoc", enc["id"], s, post_hoc_check(s.text, s.section, turns)))

    return rows, latencies, failures


def build_review_sample(rows: list[dict], per_system: int = 50, seed: int = 0):
    """Blind sample for hand labeling: the labeler does not see which system wrote each sentence."""
    rng = random.Random(seed)
    pools = {
        "baseline": [r for r in rows if r["system"] == "baseline" and r["check"] == "posthoc"],
        "grounded": [r for r in rows if r["system"] == "grounded" and r["check"] == "citation"],
    }
    picked = []
    for system, pool in pools.items():
        picked += [(system, r) for r in rng.sample(pool, min(per_system, len(pool)))]
    rng.shuffle(picked)

    review, key = [], {}
    for i, (system, r) in enumerate(picked):
        item_id = f"item_{i:03d}"
        key[item_id] = {"system": system, "flagged": r["flagged"]}
        review.append(
            {
                "item_id": item_id,
                "encounter_id": r["encounter_id"],
                "section": r["section"],
                "text": r["text"],
                "human_label": None,  # fill in: "supported", "unsupported" or "unclear"
                "missing_or_wrong_detail": "",
            }
        )
    return review, key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="results")
    parser.add_argument("--provider", choices=["gemini", "anthropic"], default=None, help="LLM provider (default: auto-detected or gemini)")
    args = parser.parse_args()

    from src.llm import get_llm_call, make_anthropic_call, make_gemini_call

    if args.provider == "anthropic":
        call_llm = make_anthropic_call()
    elif args.provider == "gemini":
        call_llm = make_gemini_call()
    else:
        call_llm = get_llm_call()

    encounters = load_encounters(args.data, args.n, args.seed)
    rows, latencies, failures = run(encounters, call_llm)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "per_sentence.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    summary = summarize(rows, latencies, failures)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    review, key = build_review_sample(rows, seed=args.seed)
    with open(out / "review_sample.jsonl", "w") as f:
        for item in review:
            f.write(json.dumps(item) + "\n")
    (out / "review_key.json").write_text(json.dumps(key, indent=2))

    print(format_table(summary))


if __name__ == "__main__":
    main()
