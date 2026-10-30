"""A support check that does not rely on the model's own citations.

The grounded pipeline cites turns itself, but the baseline does not, so comparing them fairly
needs a check that treats both the same way: find the transcript turns that best match each
sentence, then run the same number, negation and overlap tests against those turns.

Known gap: this cannot detect a dropped negation (a note saying "fever" when the patient said
"no fever"), because without a citation we cannot tell which turn the sentence was drawn from.
Hand labeling in week 4 is what covers that case.
"""

from .grounding import CLINICIAN_LABELS, MIN_OVERLAP, content_words, has_negation, numbers
from .schemas import Turn


def best_turns(text: str, turns: list[Turn], k: int = 2) -> list[Turn]:
    words = content_words(text)
    if not words:
        return []
    scored = sorted(turns, key=lambda t: len(words & content_words(t.text)), reverse=True)
    return [t for t in scored[:k] if words & content_words(t.text)]


def post_hoc_check(text: str, section: str, turns: list[Turn], k: int = 2) -> list[str]:
    top = best_turns(text, turns, k)
    if not top:
        return ["no_matching_turn"]

    source = " ".join(t.text for t in top)
    reasons: list[str] = []

    missing = numbers(text) - numbers(source)
    if missing:
        reasons.append("numbers_not_in_source:" + ",".join(sorted(missing)))

    if has_negation(text) and not has_negation(source):
        reasons.append("negation_not_in_source")

    words = content_words(text)
    overlap = len(words & content_words(source)) / len(words)
    if overlap < MIN_OVERLAP[section]:
        reasons.append(f"low_overlap:{overlap:.2f}")

    if section in {"A", "P"} and not any(t.speaker.lower() in CLINICIAN_LABELS for t in top):
        reasons.append("assessment_or_plan_not_from_clinician")

    return reasons
