"""Check a key facts file before you trust any recall number computed from it.

Usage (from the project root):
    python -m eval.lint_key_facts --facts data/key_facts_eval.jsonl --data data/encounters_eval.jsonl

Errors (exit code 1):
    malformed fact, unknown category, or a fact whose terms never appear in the transcript
    (gold facts must be things that were actually said aloud)
Warnings:
    label that looks like two facts, long term lists, terms only found in different turns,
    synonyms you may have forgotten (for example "review" without "follow up"),
    a negative fact without require_negation, and unusual fact counts per encounter.

Fact format (one encounter per line):
    {"id": "enc_001", "facts": [
        {"label": "itchy skin", "category": "symptom", "any_of": [["itch"]]},
        {"label": "duration 4 days", "category": "duration", "any_of": [["4 day"]]},
        {"label": "no fever", "category": "negative", "any_of": [["fever"]], "require_negation": true},
        {"label": "follow up in 3 to 4 days", "category": "followup",
         "any_of": [["follow up", "3"], ["review", "3"], ["see you again", "3"]]}
    ]}
Write one idea per fact (so a model that splits "itchy skin for 4 days" into two sentences still
scores), use word stems ("itch" matches itchy and itching), and list the plausible phrasings.
"""

import argparse
import json
import sys

from src.textnorm import normalize

ALLOWED_CATEGORIES = {
    "symptom", "negative", "duration", "medication", "allergy", "history", "social",
    "vital", "exam", "diagnosis", "plan", "followup",
}

SYNONYM_GROUPS = [
    ["review", "follow up", "see you again", "come back", "check up"],
    ["itch", "itchy", "itching"],
    ["tablet", "pill", "capsule"],
    ["stomach", "abdomen", "abdominal", "tummy"],
    ["headache", "head pain"],
]


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def lint(facts_by_enc: list[dict], transcripts: dict[str, list[dict]]):
    errors, warnings = [], []
    for rec in facts_by_enc:
        enc_id = rec.get("id")
        turns = transcripts.get(enc_id)
        where = f"[{enc_id}]"
        if turns is None:
            errors.append(f"{where} encounter not found in the data file")
            continue
        facts = rec.get("facts", [])
        if not 5 <= len(facts) <= 12:
            warnings.append(f"{where} has {len(facts)} facts (5 to 10 is a good range)")
        turn_texts = [normalize(t["text"]) for t in turns]
        transcript_text = " ".join(turn_texts)

        for fact in facts:
            label = fact.get("label", "<no label>")
            tag = f"{where} '{label}'"
            alternatives = fact.get("any_of")
            if not fact.get("label") or fact.get("category") not in ALLOWED_CATEGORIES:
                errors.append(f"{tag}: needs a label and a category from {sorted(ALLOWED_CATEGORIES)}")
            if not alternatives or not all(isinstance(a, list) and a and all(isinstance(t, str) and t.strip() for t in a) for a in alternatives):
                errors.append(f"{tag}: any_of must be a non-empty list of non-empty term lists")
                continue

            normalized = [[normalize(t) for t in alt] for alt in alternatives]
            same_turn = any(all(term in tt for term in alt) for alt in normalized for tt in turn_texts)
            anywhere = any(all(term in transcript_text for term in alt) for alt in normalized)
            if not anywhere:
                errors.append(f"{tag}: terms never appear in the transcript, so this fact was not said aloud")
            elif not same_turn:
                warnings.append(f"{tag}: terms only appear in different turns, check the fact is stated that way")

            if " and " in label.lower() or "," in label:
                warnings.append(f"{tag}: label looks like more than one fact, consider splitting it")
            if any(len(alt) > 3 for alt in alternatives):
                warnings.append(f"{tag}: an alternative has more than 3 terms, which makes it easy to miss")
            if fact.get("category") == "negative" and not fact.get("require_negation"):
                warnings.append(f"{tag}: negative fact without require_negation, 'fever' would count as recalled")

            flat = {t for alt in normalized for t in alt}
            for group in SYNONYM_GROUPS:
                group_n = [normalize(g) for g in group]
                hit = [g for g in group_n if g in flat]
                if hit and len(hit) < len(group_n) and fact.get("category") in {"plan", "followup", "symptom", "medication"}:
                    missing = [g for g in group_n if g not in flat]
                    warnings.append(f"{tag}: also consider phrasings {missing}")
    return errors, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", required=True)
    parser.add_argument("--data", required=True)
    args = parser.parse_args()

    transcripts = {e["id"]: e["turns"] for e in load_jsonl(args.data)}
    facts = load_jsonl(args.facts)
    errors, warnings = lint(facts, transcripts)

    covered = {r["id"] for r in facts}
    for enc_id in transcripts:
        if enc_id not in covered:
            warnings.append(f"[{enc_id}] has no facts entry")

    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("ERROR:  ", e)
    total = sum(len(r.get("facts", [])) for r in facts)
    print(f"\n{len(facts)} encounters, {total} facts, {len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
