"""Split PriMock57 dataset into a development set (encounters 1-3) and held-out set (encounters 4-57).

Usage:
    python scripts/make_split.py
"""

import json
from pathlib import Path

DEV_IDS = {
    "day1_consultation01",
    "day1_consultation02",
    "day1_consultation03",
}

DATA_PATH = Path("data/encounters.jsonl")
DEV_PATH = Path("data/encounters_dev.jsonl")
HELDOUT_PATH = Path("data/encounters_heldout.jsonl")


def main():
    with open(DATA_PATH) as f:
        encounters = [json.loads(line) for line in f if line.strip()]

    dev = []
    heldout = []
    for enc in encounters:
        if enc["id"] in DEV_IDS:
            dev.append(enc)
        else:
            heldout.append(enc)

    with open(DEV_PATH, "w") as f:
        for enc in dev:
            f.write(json.dumps(enc) + "\n")

    with open(HELDOUT_PATH, "w") as f:
        for enc in heldout:
            f.write(json.dumps(enc) + "\n")

    print(f"Created dev set: {len(dev)} encounters -> {DEV_PATH}")
    print(f"Created held-out set: {len(heldout)} encounters -> {HELDOUT_PATH}")


if __name__ == "__main__":
    main()
