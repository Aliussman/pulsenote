"""A support check that does not rely on the model's own citations (validator-v2).

The grounded pipeline cites turns itself, but the baseline does not, so comparing them fairly
needs a check that treats both the same way: find the transcript turns that best match each
sentence, then run the same number, negation and overlap tests against those turns.

Changes from v1, each found by auditing the dev-set flags:
  1. Yes/no answers: when a retrieved turn is a question, a one-word reply ("No.") right after
     it is added to the evidence, and a retrieved short reply brings in the question before it.
  2. Assessment and Plan sentences are matched against clinician turns first, so a patient
     talking about the same cream or tablet no longer outranks the doctor prescribing it.
  3. Numbers are checked against the whole transcript (NUMBERS_SCOPE = "document"), because
     a fact such as an age is often said many turns away from the symptom it is written next
     to. This is a weaker screen than the citation check and applies equally to both systems.
     Set NUMBERS_SCOPE = "top_turns" to restore the v1 behaviour.

Known gap: this cannot detect a dropped negation (a note saying "fever" when the patient said
"no fever"), because without a citation we cannot tell which turn the sentence came from.
Hand labels cover that case.
"""

from .grounding import CLINICIAN_LABELS, MIN_OVERLAP
from .schemas import Turn
from .textnorm import content_words, has_negation, numbers

NUMBERS_SCOPE = "document"  # "document" or "top_turns"
QA_MAX_WORDS = 6  # a reply this short is treated as an answer to the previous question


def best_turns(text: str, turns: list[Turn], k: int = 2, speakers: set[str] | None = None) -> list[Turn]:
    words = content_words(text)
    if not words:
        return []
    pool = [t for t in turns if speakers is None or t.speaker.lower() in speakers]
    scored = sorted(pool, key=lambda t: len(words & content_words(t.text)), reverse=True)
    return [t for t in scored[:k] if words & content_words(t.text)]


def expand_qa(selected: list[Turn], turns: list[Turn]) -> list[Turn]:
    """Add the one-word answer after a retrieved question, and the question before a retrieved short answer."""
    index = {t.id: i for i, t in enumerate(turns)}
    chosen = {t.id: t for t in selected}
    for t in selected:
        i = index[t.id]
        if i + 1 < len(turns):
            nxt = turns[i + 1]
            if nxt.speaker != t.speaker and len(nxt.text.split()) <= QA_MAX_WORDS:
                chosen[nxt.id] = nxt
        if i > 0 and len(t.text.split()) <= QA_MAX_WORDS:
            prev = turns[i - 1]
            if prev.speaker != t.speaker:
                chosen[prev.id] = prev
    return [chosen[tid] for tid in sorted(chosen, key=lambda x: index[x])]


def post_hoc_check(text: str, section: str, turns: list[Turn], k: int = 2) -> list[str]:
    clinician_section = section in {"A", "P"}
    top: list[Turn] = []
    if clinician_section:
        top = best_turns(text, turns, k, speakers=CLINICIAN_LABELS)
    if not top:
        top = best_turns(text, turns, k)
    if not top:
        return ["no_matching_turn"]

    context = expand_qa(top, turns)
    source = " ".join(t.text for t in context)
    number_source = " ".join(t.text for t in turns) if NUMBERS_SCOPE == "document" else source
    reasons: list[str] = []

    missing = numbers(text) - numbers(number_source)
    if missing:
        reasons.append("numbers_not_in_source:" + ",".join(sorted(missing)))

    if has_negation(text) and not has_negation(source):
        reasons.append("negation_not_in_source")

    words = content_words(text)
    overlap = len(words & content_words(source)) / len(words)
    if overlap < MIN_OVERLAP[section]:
        reasons.append(f"low_overlap:{overlap:.2f}")

    if clinician_section and not any(t.speaker.lower() in CLINICIAN_LABELS for t in top):
        reasons.append("assessment_or_plan_not_from_clinician")

    return reasons
