"""Cheap, deterministic checks that every note sentence is backed by the transcript.

These are heuristics. They catch the common failures (invented numbers, dropped
negations, fake quotes) but will also flag some honest paraphrases. Log the flag
reasons and review them by hand before trusting any threshold.
"""

import re
from collections import Counter
from difflib import SequenceMatcher

from .schemas import NoteSentence, RawNote, RawSentence, SOAPNote, Turn
from .textnorm import content_words, has_negation, normalize, numbers

CLINICIAN_LABELS = {"doctor", "clinician", "physician", "dr", "gp", "nurse"}


HARD_REASON_CODES = {
    "quote_not_in_turn",
    "numbers_not_in_source",
    "possible_dropped_negation",
    "negation_not_in_quote",
    "negation_not_in_source",
    "assessment_or_plan_not_from_clinician",
    "unknown_turn",
    "no_support",
    "no_matching_turn",
}


def is_hard_failure(reason: str) -> bool:
    """True if reason represents a factual distortion (invented number, dropped negation, fake quote, wrong speaker)."""
    return reason.split(":")[0] in HARD_REASON_CODES

# Minimum share of a sentence's content words that must appear in the cited turns.
MIN_OVERLAP = {"S": 0.5, "O": 0.5, "A": 0.4, "P": 0.4}







def quote_matches(quote: str, turn_text: str, threshold: float = 0.9) -> bool:
    """True if the quote appears in the turn, allowing for small punctuation or typo drift."""
    q, t = normalize(quote), normalize(turn_text)
    if not q:
        return False
    if q in t:
        return True
    q_words, t_words = q.split(), t.split()
    n = len(q_words)
    best = 0.0
    for i in range(max(1, len(t_words) - n + 1)):
        window = " ".join(t_words[i : i + n])
        best = max(best, SequenceMatcher(None, q, window).ratio())
    return best >= threshold


def validate_sentence(s: RawSentence, turns_by_id: dict[int, Turn]) -> list[str]:
    if not s.support:
        return ["no_support"]

    reasons: list[str] = []
    cited: list[Turn] = []
    for sup in s.support:
        turn = turns_by_id.get(sup.turn_id)
        if turn is None:
            reasons.append(f"unknown_turn:{sup.turn_id}")
            continue
        cited.append(turn)
        if not quote_matches(sup.quote, turn.text):
            reasons.append(f"quote_not_in_turn:{sup.turn_id}")

    if not cited:
        return reasons

    source_text = " ".join(t.text for t in cited)
    quotes_text = " ".join(sup.quote for sup in s.support)

    # 1. Numbers, doses and durations in the sentence must exist in the source.
    missing = numbers(s.text) - numbers(source_text)
    if missing:
        reasons.append("numbers_not_in_source:" + ",".join(sorted(missing)))

    # 2. Negation should match between the sentence and the quoted evidence.
    note_neg, quote_neg = has_negation(s.text), has_negation(quotes_text)
    if quote_neg and not note_neg:
        reasons.append("possible_dropped_negation")
    elif note_neg and not quote_neg:
        reasons.append("negation_not_in_quote")

    # 3. Most content words should appear in the cited turns.
    # If cited turns are brief replies (e.g. "No", "Yes", "None"), include the immediate
    # question turn (turn_id - 1) in overlap context to credit dialogue Q&A context.
    overlap_turns = list(cited)
    for t in cited:
        if len(t.text.split()) <= 6 and (t.id - 1) in turns_by_id:
            prec = turns_by_id[t.id - 1]
            if prec not in overlap_turns:
                overlap_turns.append(prec)
    overlap_source_text = " ".join(t.text for t in overlap_turns)

    words = content_words(s.text)
    if words:
        overlap = len(words & content_words(overlap_source_text)) / len(words)
        if overlap < MIN_OVERLAP[s.section]:
            reasons.append(f"low_overlap:{overlap:.2f}")

    # 4. Assessment and plan statements should come from the clinician.
    if s.section in {"A", "P"} and not any(t.speaker.lower() in CLINICIAN_LABELS for t in cited):
        reasons.append("assessment_or_plan_not_from_clinician")

    return reasons


def validate_note(raw: RawNote, turns: list[Turn]) -> SOAPNote:
    turns_by_id = {t.id: t for t in turns}
    out: list[NoteSentence] = []
    for s in raw.sentences:
        reasons = validate_sentence(s, turns_by_id)
        hard = [r for r in reasons if is_hard_failure(r)]
        soft = [r for r in reasons if not is_hard_failure(r)]
        out.append(
            NoteSentence(
                **s.model_dump(),
                flagged=bool(hard),
                flag_reasons=reasons,
                hard_flags=hard,
                soft_flags=soft,
            )
        )
    return SOAPNote(sentences=out)


def support_rate(note: SOAPNote) -> float:
    """Share of sentences that passed every check."""
    if not note.sentences:
        return 0.0
    return sum(not s.flagged for s in note.sentences) / len(note.sentences)


def flag_summary(note: SOAPNote) -> Counter:
    """Counts of each flag type, useful for the eval table."""
    return Counter(r.split(":")[0] for s in note.sentences for r in s.flag_reasons)
