"""Stratum-weighted scoring of hand labels from a stratified review sample.

A stratified sample deliberately over-represents hard-flagged sentences, so a plain
"unsupported / judged" rate is biased upward. This script weights each stratum back to its
true share of the population:

    estimate = sum_h (N_h / N) * (unsupported_h / judged_h)

where N_h is the number of sentences in stratum h in the FULL set of rescored rows, and the
strata are hard (any hard reason), soft (soft warnings only) and clean (no flags).

Usage (from the project root):
    python -m eval.score_labels_stratified \
        --labels results/labels_stratified.jsonl \
        --key results/review_key_stratified.json \
        --rows results/held_out/per_sentence_rescored.jsonl \
        --split data/split.json --only heldout

Important:
  * --rows must be the same rescored rows the sample was drawn from, scored by the same
    validator version. The stratum of each labeled sentence is looked up in these rows
    (by system, encounter and text), not taken from the key, so a validator change after
    sampling cannot silently corrupt the weights.
  * "unclear" labels are left out of the main estimate. Lower and upper bounds that count
    them as supported or unsupported are reported next to it.
  * The bootstrap resamples labeled sentences inside each stratum. Sentences from one
    conversation are correlated, so treat the intervals as somewhat optimistic.
"""

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from eval.stats import wilson

STRATA = ("hard", "soft", "clean")
SYSTEM_CHECK = {"baseline": "posthoc", "grounded": "citation"}


def stratum_of(row: dict) -> str:
    if "hard_reasons" not in row:
        raise SystemExit("Rows need hard_reasons and soft_reasons. Run python -m eval.rescore first.")
    if row["hard_reasons"]:
        return "hard"
    return "soft" if row["soft_reasons"] else "clean"


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def population(rows: list[dict], allowed_encounters: set[str] | None = None):
    """Stratum counts per system, and a lookup from (system, encounter, text) to stratum."""
    counts = {s: Counter() for s in SYSTEM_CHECK}
    index: dict[tuple, str] = {}
    for r in rows:
        system = r["system"]
        if SYSTEM_CHECK.get(system) != r["check"]:
            continue
        if allowed_encounters is not None and r["encounter_id"] not in allowed_encounters:
            continue
        stratum = stratum_of(r)
        counts[system][stratum] += 1
        index.setdefault((system, r["encounter_id"], r["text"]), stratum)
    return counts, index


def outcomes_by_stratum(labels: list[dict], key: dict, index: dict):
    """outcomes[system][stratum] = list of 'supported' / 'unsupported' / 'unclear'."""
    out = {s: {h: [] for h in STRATA} for s in SYSTEM_CHECK}
    unmatched = Counter()
    for rec in labels:
        system = key[rec["item_id"]]["system"]
        stratum = index.get((system, rec["encounter_id"], rec["text"]))
        if stratum is None:
            unmatched[system] += 1
            continue
        out[system][stratum].append(rec["human_label"])
    return out, unmatched


def to_values(labels: list[str], mode: str) -> list[int]:
    """1 = unsupported. mode: primary drops unclear; lower counts it supported; upper counts it unsupported."""
    vals = []
    for lab in labels:
        if lab == "unclear":
            if mode == "primary":
                continue
            vals.append(1 if mode == "upper" else 0)
        else:
            vals.append(1 if lab == "unsupported" else 0)
    return vals


def estimates(values: dict[str, list[int]], pop: Counter):
    """Weighted unsupported rate, share of unsupported sentences that were hard-flagged, and that were flagged at all."""
    total = sum(pop[h] for h in STRATA)
    missing = [h for h in STRATA if pop[h] > 0 and not values[h]]
    if missing or total == 0:
        return None, missing
    mass = {h: pop[h] * sum(values[h]) / len(values[h]) for h in STRATA if pop[h] > 0}
    unsupported_total = sum(mass.values())
    rate = unsupported_total / total
    recall_hard = mass.get("hard", 0.0) / unsupported_total if unsupported_total else None
    recall_any = (mass.get("hard", 0.0) + mass.get("soft", 0.0)) / unsupported_total if unsupported_total else None
    return {"rate": rate, "recall_hard": recall_hard, "recall_any": recall_any}, []


def percentile_ci(samples: list[float]):
    samples = sorted(samples)
    if not samples:
        return None
    n = len(samples)
    return [samples[int(0.025 * n)], samples[max(int(0.975 * n) - 1, 0)]]


def score_system(outcomes: dict[str, list[str]], pop: Counter, boot: int, seed: int) -> dict:
    primary = {h: to_values(outcomes[h], "primary") for h in STRATA}
    result: dict = {
        "population": {h: pop[h] for h in STRATA},
        "labeled": {h: len(outcomes[h]) for h in STRATA},
        "judged": {h: len(primary[h]) for h in STRATA},
        "unclear": {h: outcomes[h].count("unclear") for h in STRATA},
        "per_stratum": {},
    }
    for h in STRATA:
        n, k = len(primary[h]), sum(primary[h])
        lo, hi = wilson(k, n)
        result["per_stratum"][h] = {"unsupported": k, "judged": n, "rate": k / n if n else None, "wilson_95ci": [lo, hi]}

    point, missing = estimates(primary, pop)
    if point is None:
        result["error"] = f"no labeled sentences in stratum {missing}" if missing else "empty population"
        return result

    rng = random.Random(seed)
    draws: dict[str, list[float]] = {"rate": [], "recall_hard": [], "recall_any": []}
    for _ in range(boot):
        resampled = {h: [rng.choice(primary[h]) for _ in primary[h]] if primary[h] else [] for h in STRATA}
        est, _ = estimates(resampled, pop)
        if est:
            for name in draws:
                if est[name] is not None:
                    draws[name].append(est[name])

    result["weighted_unsupported_rate"] = point["rate"]
    result["weighted_unsupported_rate_95ci"] = percentile_ci(draws["rate"])
    result["unclear_bounds"] = {}
    for mode in ("lower", "upper"):
        bound, _ = estimates({h: to_values(outcomes[h], mode) for h in STRATA}, pop)
        result["unclear_bounds"][mode] = bound["rate"] if bound else None
    result["validator_hard_flag_precision"] = result["per_stratum"]["hard"]
    result["validator_clean_miss_rate"] = result["per_stratum"]["clean"]
    result["share_of_unsupported_that_was_hard_flagged"] = point["recall_hard"]
    result["share_of_unsupported_that_was_hard_flagged_95ci"] = percentile_ci(draws["recall_hard"])
    result["share_of_unsupported_that_had_any_flag"] = point["recall_any"]
    result["share_of_unsupported_that_had_any_flag_95ci"] = percentile_ci(draws["recall_any"])
    return result


def score(labels: list[dict], key: dict, rows: list[dict], allowed_encounters: set[str] | None = None, boot: int = 2000, seed: int = 0) -> dict:
    pops, index = population(rows, allowed_encounters)
    outcomes, unmatched = outcomes_by_stratum(labels, key, index)
    out = {system: score_system(outcomes[system], pops[system], boot, seed) for system in SYSTEM_CHECK}
    out["unmatched_labels"] = dict(unmatched)
    return out


def pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def format_report(summary: dict) -> str:
    lines = []
    for system in SYSTEM_CHECK:
        s = summary[system]
        lines.append(f"\n{system}")
        lines.append("  stratum   population  labeled  judged  unsupported  rate     wilson 95% CI")
        for h in STRATA:
            p = s["per_stratum"][h]
            lo, hi = p["wilson_95ci"]
            lines.append(
                f"  {h:<8} {s['population'][h]:>10} {s['labeled'][h]:>8} {s['judged'][h]:>7} "
                f"{p['unsupported']:>11}  {pct(p['rate']):>7}  {lo:.1%} to {hi:.1%}"
            )
        if "error" in s:
            lines.append(f"  cannot weight: {s['error']}")
            continue
        ci = s["weighted_unsupported_rate_95ci"]
        lines.append(f"  weighted unsupported rate: {pct(s['weighted_unsupported_rate'])}  (95% bootstrap CI {pct(ci[0])} to {pct(ci[1])})")
        lines.append(f"  if unclear were all supported / all unsupported: {pct(s['unclear_bounds']['lower'])} / {pct(s['unclear_bounds']['upper'])}")
        r1, r2 = s["share_of_unsupported_that_was_hard_flagged_95ci"], s["share_of_unsupported_that_had_any_flag_95ci"]
        lines.append(f"  share of unsupported sentences the hard flags caught: {pct(s['share_of_unsupported_that_was_hard_flagged'])}  ({pct(r1[0])} to {pct(r1[1])})")
        lines.append(f"  share caught by any flag (hard or soft): {pct(s['share_of_unsupported_that_had_any_flag'])}  ({pct(r2[0])} to {pct(r2[1])})")
    if summary["unmatched_labels"]:
        lines.append(f"\nwarning: labels not found in --rows (skipped): {summary['unmatched_labels']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="results/labels_stratified.jsonl")
    parser.add_argument("--key", default="results/review_key_stratified.json")
    parser.add_argument("--rows", required=True, help="rescored rows the sample was drawn from")
    parser.add_argument("--split", default=None)
    parser.add_argument("--only", choices=["dev", "heldout"], default=None)
    parser.add_argument("--out", default="results/label_summary_stratified.json")
    parser.add_argument("--boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    allowed = None
    if args.only:
        if not args.split:
            raise SystemExit("--only needs --split")
        allowed = set(json.loads(Path(args.split).read_text())[args.only])

    summary = score(load_jsonl(args.labels), json.loads(Path(args.key).read_text()), load_jsonl(args.rows), allowed, args.boot, args.seed)
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(format_report(summary))


if __name__ == "__main__":
    main()
