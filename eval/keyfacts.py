"""Key-fact recall: of the facts that must appear in the note, how many did each system capture?

Key facts live in a JSONL file, one encounter per line:

    {"id": "enc_001", "facts": [
        {"label": "cough for 2 weeks", "category": "symptom", "any_of": [["cough", "2 week"]]},
        {"label": "no fever", "category": "symptom", "any_of": [["fever"]], "require_negation": true}
    ]}

A fact counts as recalled if some single note sentence contains every term in at least one of
its alternatives (the inner lists). Terms are matched as substrings after normalisation, so write
word stems ("week" matches "weeks") and digits ("2" also matches "two"). Set require_negation
for facts like "no fever" so that a sentence saying "fever" does not count.

Limit: a fact split across two sentences will be missed. Keep terms short and put alternatives
in any_of so honest phrasing differences still match.
"""

import json
from collections import defaultdict

from src.grounding import has_negation, normalize


def load_key_facts(path: str) -> dict[str, list[dict]]:
    with open(path) as f:
        return {rec["id"]: rec["facts"] for rec in map(json.loads, filter(str.strip, f))}


def fact_recalled(fact: dict, sentences: list[str]) -> bool:
    alternatives = [[normalize(term) for term in alt] for alt in fact["any_of"]]
    for sentence in sentences:
        text = normalize(sentence)
        if fact.get("require_negation") and not has_negation(sentence):
            continue
        if any(all(term in text for term in alt) for alt in alternatives):
            return True
    return False


def collect_sentences(rows: list[dict]):
    """Group note sentences by system variant and encounter, using the check that fits each system."""
    variants: dict[str, dict[str, list[str]]] = {
        "baseline": defaultdict(list),
        "grounded_all": defaultdict(list),
        "grounded_unflagged": defaultdict(list),
    }
    for r in rows:
        enc = r["encounter_id"]
        if r["system"] == "baseline" and r["check"] == "posthoc":
            variants["baseline"][enc].append(r["text"])
        elif r["system"] == "grounded" and r["check"] == "citation":
            # Mark the encounter as present even if every sentence ends up flagged.
            variants["grounded_all"].setdefault(enc, [])
            variants["grounded_unflagged"].setdefault(enc, [])
            variants["grounded_all"][enc].append(r["text"])
            if not r["flagged"]:
                variants["grounded_unflagged"][enc].append(r["text"])
    return variants


def compute_recall(rows: list[dict], facts_by_enc: dict[str, list[dict]]) -> dict:
    out = {}
    for variant, by_enc in collect_sentences(rows).items():
        recalled = total = 0
        by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        missed = []
        scored = [enc for enc in by_enc if enc in facts_by_enc]
        for enc in scored:
            for fact in facts_by_enc[enc]:
                hit = fact_recalled(fact, by_enc[enc])
                total += 1
                recalled += hit
                cat = fact.get("category", "other")
                by_category[cat][1] += 1
                by_category[cat][0] += hit
                if not hit:
                    missed.append({"encounter_id": enc, "fact": fact["label"]})
        out[variant] = {
            "encounters_scored": len(scored),
            "recalled": recalled,
            "total": total,
            "recall": recalled / total if total else 0.0,
            "by_category": {c: {"recalled": v[0], "total": v[1]} for c, v in sorted(by_category.items())},
            "missed": missed,
        }
    return out
