"""Pick the held-out encounters to evaluate BEFORE running any model on them.

Choosing the sample first, with a fixed seed, and committing the result means nobody can
(or can be accused of) picking encounters after seeing how the system did on them.

Usage (from the project root):
    python scripts/pick_heldout.py --n 20 --seed 20261101
    git add data/split_eval.json data/encounters_eval.jsonl && git commit -m "Pre-register held-out sample"

Outputs:
    data/split_eval.json        {"seed": ..., "n": ..., "eval": [ids]}
    data/encounters_eval.jsonl  just those encounters, ready for eval.run_eval
"""

import argparse
import json
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/encounters.jsonl")
    parser.add_argument("--split", default="data/split.json", help="split with a heldout list")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--split-out", default="data/split_eval.json")
    parser.add_argument("--data-out", default="data/encounters_eval.jsonl")
    args = parser.parse_args()

    heldout = sorted(json.loads(Path(args.split).read_text())["heldout"])
    if args.n > len(heldout):
        raise SystemExit(f"Asked for {args.n} but only {len(heldout)} held-out encounters exist.")
    chosen = sorted(random.Random(args.seed).sample(heldout, args.n))

    with open(args.data) as f:
        encounters = {e["id"]: e for e in map(json.loads, filter(str.strip, f))}
    missing = [c for c in chosen if c not in encounters]
    if missing:
        raise SystemExit(f"Not found in {args.data}: {missing}")

    Path(args.split_out).write_text(json.dumps({"seed": args.seed, "n": args.n, "eval": chosen}, indent=2))
    with open(args.data_out, "w") as f:
        for enc_id in chosen:
            f.write(json.dumps(encounters[enc_id]) + "\n")
    print(f"picked {len(chosen)} of {len(heldout)} held-out encounters with seed {args.seed}:")
    print(", ".join(chosen))


if __name__ == "__main__":
    main()
