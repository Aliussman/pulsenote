"""Cheap, deterministic checks that every note sentence is backed by the transcript.

These are heuristics. They catch the common failures (invented numbers, dropped
negations, fake quotes) but will also flag some honest paraphrases. Log the flag
reasons and review them by hand before trusting any threshold.
"""

import re
from collections import Counter
from difflib import SequenceMatcher

from .schemas import NoteSentence, RawNote, RawSentence, SOAPNote, Turn

CLINICIAN_LABELS = {"doctor", "clinician", "physician", "dr", "gp", "nurse"}

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}

NEGATION_CUES = {"no", "not", "denies", "denied", "without", "never", "none", "negative", "nothing"}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "has", "have", "had", "was", "were", "are",
    "his", "her", "she", "him", "from", "into", "than", "then", "also", "will", "been",
    "patient", "reports", "reported", "states", "stated", "noted", "presents", "presenting",
    "history", "doctor", "clinician", "plan", "per",
}

# Minimum share of a sentence's content words that must appear in the cited turns.
# A and P are lower because clinicians summarise and the note may rephrase more.
MIN_OVERLAP = {"S": 0.6, "O": 0.6, "A": 0.4, "P": 0.4}

NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def normalize(text: str) -> str:
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"n't\b", " not", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # drop periods, keep decimals
    text = re.sub(r"[^a-z0-9.\s]", " ", text)
    return " ".join(NUMBER_WORDS.get(tok, tok) for tok in text.split())


def stem(tok: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if tok.endswith(suffix) and len(tok) - len(suffix) >= 3:
            return tok[: -len(suffix)]
    return tok


def content_words(text: str) -> set[str]:
    return {
        stem(t)
        for t in normalize(text).split()
        if t not in STOPWORDS and not t.replace(".", "").isdigit() and len(t) > 2
    }


def numbers(text: str) -> set[str]:
    return set(NUM_RE.findall(normalize(text)))


def has_negation(text: str) -> bool:
    return bool(set(normalize(text).split()) & NEGATION_CUES)


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
    words = content_words(s.text)
    if words:
        overlap = len(words & content_words(source_text)) / len(words)
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
        out.append(NoteSentence(**s.model_dump(), flagged=bool(reasons), flag_reasons=reasons))
    return SOAPNote(sentences=out)


def support_rate(note: SOAPNote) -> float:
    """Share of sentences that passed every check."""
    if not note.sentences:
        return 0.0
    return sum(not s.flagged for s in note.sentences) / len(note.sentences)


def flag_summary(note: SOAPNote) -> Counter:
    """Counts of each flag type, useful for the eval table."""
    return Counter(r.split(":")[0] for s in note.sentences for r in s.flag_reasons)
