# validator-v2 patch

## Files (copy into your repo, same paths)

New:
- src/textnorm.py                      shared stemmer, number words, negation cues
- eval/score_labels_stratified.py      stratum-weighted scoring of the stratified review sample
- eval/lint_key_facts.py               checks a key facts file before you trust recall numbers
- scripts/pick_heldout.py              seeded, pre-registered held-out sample
- scripts/draft_key_facts.py           worksheet and skeleton for writing gold facts
- scripts/apply_v2_imports.py          points src/grounding.py at src/textnorm.py
- tests/test_v2_fixes.py, tests/test_stratified.py, tests/test_keyfact_tools.py

Replaced (merge by hand if you edited it since v1):
- src/posthoc.py

## Steps

1. Copy the files in. If your src/posthoc.py has changes beyond v1, diff it against the new one first.
2. python scripts/apply_v2_imports.py --dry-run   then without --dry-run
   (removes the old text helpers from src/grounding.py, adds one import, writes a .bak)
3. pytest -q    (everything should pass; if your own tests assert v1 stemmer or number
   behaviour, update them: "lives" now stems to "liv" like "live", and "one" is only a number
   before a unit or in a range)
4. python -m eval.rescore ... on the dev set. Expect the post-hoc numbers to move for BOTH
   systems. Record the new dev table in the README, labeled validator-v2.
5. git commit, git tag validator-v2, then:  git diff validator-v2 -- src/   must stay empty from here on.
6. python scripts/pick_heldout.py --n 20 --seed <any number you write down now>
   commit data/split_eval.json and data/encounters_eval.jsonl BEFORE running any model.
7. python scripts/draft_key_facts.py, write data/key_facts_eval.jsonl from the worksheet,
   then python -m eval.lint_key_facts --facts data/key_facts_eval.jsonl --data data/encounters_eval.jsonl
   Commit it before you look at any model output for these encounters.

## Behaviour changes in v2

- stem: "lives/live/living/lived" share one stem
- "one" is the number 1 only before a unit or in a range ("one to two weeks"); compound
  numbers ("thirty one") become digits
- post-hoc: a one-word reply after a retrieved question is included as evidence
- post-hoc: Assessment and Plan sentences retrieve clinician turns first
- post-hoc: numbers are checked against the whole transcript (NUMBERS_SCOPE in src/posthoc.py)
  This is a weaker screen than the citation check. Say so in the README.
- negation cues also include deny/denying (v1 plus your audit additions)
