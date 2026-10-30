"""Turn hand labels into the headline numbers.

Usage: python -m eval.score_labels
Reads results/labels.jsonl and results/review_key.json, writes results/label_summary.json.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from eval.stats import wilson


def score(labels: list[dict], key: dict[str, dict]) -> dict:
    by_system: dict[str, Counter] = defaultdict(Counter)
    confusion: dict[str, Counter] = defaultdict(Counter)

    for rec in labels:
        info = key[rec["item_id"]]
        system, flagged, label = info["system"], info["flagged"], rec["human_label"]
        by_system[system][label] += 1
        if label in {"supported", "unsupported"}:
            # How well does the automated check agree with the human?
            if flagged and label == "unsupported":
                confusion[system]["flagged_and_unsupported"] += 1
            elif flagged and label == "supported":
                confusion[system]["flagged_but_supported"] += 1  # false alarm
            elif not flagged and label == "unsupported":
                confusion[system]["missed_unsupported"] += 1  # check missed it
            else:
                confusion[system]["passed_and_supported"] += 1

    out = {}
    for system, c in by_system.items():
        judged = c["supported"] + c["unsupported"]
        low, high = wilson(c["unsupported"], judged)
        cf = confusion[system]
        caught, missed = cf["flagged_and_unsupported"], cf["missed_unsupported"]
        out[system] = {
            "labeled": sum(c.values()),
            "supported": c["supported"],
            "unsupported": c["unsupported"],
            "unclear": c["unclear"],
            "unsupported_rate": c["unsupported"] / judged if judged else 0.0,
            "unsupported_rate_95ci": [low, high],
            "automated_check": {
                **dict(cf),
                "recall_of_unsupported": caught / (caught + missed) if (caught + missed) else None,
                "precision_of_flags": caught / (caught + cf["flagged_but_supported"])
                if (caught + cf["flagged_but_supported"])
                else None,
            },
        }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="results/labels.jsonl")
    parser.add_argument("--key", default="results/review_key.json")
    parser.add_argument("--out", default="results/label_summary.json")
    args = parser.parse_args()

    with open(args.labels) as f:
        labels = [json.loads(line) for line in f if line.strip()]
    key = json.loads(Path(args.key).read_text())

    summary = score(labels, key)
    Path(args.out).write_text(json.dumps(summary, indent=2))

    for system, s in summary.items():
        lo, hi = s["unsupported_rate_95ci"]
        print(f"{system}: {s['unsupported']} unsupported out of {s['supported'] + s['unsupported']} judged "
              f"({s['unsupported_rate']:.1%}, 95% CI {lo:.1%} to {hi:.1%}), {s['unclear']} unclear")
        a = s["automated_check"]
        rec, prec = a["recall_of_unsupported"], a["precision_of_flags"]
        print(f"  automated check: caught {a.get('flagged_and_unsupported', 0)}, "
              f"missed {a.get('missed_unsupported', 0)}, false alarms {a.get('flagged_but_supported', 0)}"
              + (f", recall {rec:.0%}" if rec is not None else "")
              + (f", precision {prec:.0%}" if prec is not None else ""))


if __name__ == "__main__":
    main()
