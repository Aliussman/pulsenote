from collections import Counter, defaultdict
from statistics import mean, median


def summarize(rows: list[dict], latencies: dict[str, list[float]], failures: dict[str, int]) -> dict:
    """rows: one dict per note sentence per check, see run_eval.make_row."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["system"], r["check"])].append(r)

    out: dict = {"checks": {}, "latency_seconds": {}, "failed_encounters": failures}
    for (system, check), rs in sorted(groups.items()):
        total = len(rs)
        passed = sum(not r["flagged"] for r in rs)
        reasons = Counter(x.split(":")[0] for r in rs for x in r["reasons"])
        out["checks"][f"{system}/{check}"] = {
            "sentences": total,
            "passed": passed,
            "pass_rate": passed / total if total else 0.0,
            "flag_reasons": dict(reasons),
        }
    for system, vals in latencies.items():
        if vals:
            out["latency_seconds"][system] = {
                "mean": mean(vals),
                "median": median(vals),
                "max": max(vals),
                "n": len(vals),
            }
    return out


def format_table(summary: dict) -> str:
    lines = ["check                      passed / total   rate"]
    for name, s in summary["checks"].items():
        lines.append(f"{name:<26} {s['passed']:>4} / {s['sentences']:<8} {s['pass_rate']:.1%}")
    lines.append("")
    lines.append("end-to-end latency (seconds)")
    for system, s in summary["latency_seconds"].items():
        lines.append(f"{system:<10} mean {s['mean']:.1f}  median {s['median']:.1f}  max {s['max']:.1f}  (n={s['n']})")
    if any(summary["failed_encounters"].values()):
        lines.append(f"failed encounters: {summary['failed_encounters']}")
    return "\n".join(lines)
