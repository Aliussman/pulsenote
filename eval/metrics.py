from collections import Counter, defaultdict
from statistics import mean, median

from eval.stats import wilson


def summarize(rows: list[dict], latencies: dict[str, list[float]], failures: dict[str, int]) -> dict:
    """rows: one dict per note sentence per check, see run_eval.make_row."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["system"], r["check"])].append(r)

    out: dict = {"checks": {}, "latency_seconds": {}, "failed_encounters": failures}
    for (system, check), rs in sorted(groups.items()):
        total = len(rs)
        passed_clean = sum(not r["reasons"] for r in rs)
        hard_count = sum(bool(r.get("hard_reasons", [x for x in r["reasons"] if not x.startswith("low_overlap")])) for r in rs)
        hard_rate = hard_count / total if total else 0.0
        ci_low, ci_high = wilson(hard_count, total) if total else (0.0, 0.0)
        reasons = Counter(x.split(":")[0] for r in rs for x in r["reasons"])
        out["checks"][f"{system}/{check}"] = {
            "sentences": total,
            "passed": passed_clean,
            "pass_rate": passed_clean / total if total else 0.0,
            "hard_failures": hard_count,
            "hard_failure_rate": hard_rate,
            "hard_failure_ci_95": [ci_low, ci_high],
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
    lines = [f"{'check':<24} {'clean pass':<16} {'hard failures':<16} {'95% CI':<18}"]
    for name, s in summary["checks"].items():
        clean_str = f"{s['passed']}/{s['sentences']} ({s['pass_rate']:.1%})"
        ci = s.get("hard_failure_ci_95", [0.0, 0.0])
        hard_str = f"{s.get('hard_failures', 0)}/{s['sentences']} ({s.get('hard_failure_rate', 0.0):.1%})"
        ci_str = f"[{ci[0]:.1%} - {ci[1]:.1%}]"
        lines.append(f"{name:<24} {clean_str:<16} {hard_str:<16} {ci_str:<18}")
    lines.append("")
    lines.append("end-to-end latency (seconds)")
    for system, s in summary["latency_seconds"].items():
        lines.append(f"{system:<10} mean {s['mean']:.1f}  median {s['median']:.1f}  max {s['max']:.1f}  (n={s['n']})")
    if any(summary["failed_encounters"].values()):
        lines.append(f"failed encounters: {summary['failed_encounters']}")
    return "\n".join(lines)
