"""Shared text normalisation for the grounding validator and the post-hoc check (validator-v2).

Both checks import from here, so a fix to number handling, stemming or negation applies to
every system in the same way. Changes from v1, each found by the dev-set audit:

  1. stem(): "lives", "live" and "living" now share one stem (v1 turned "lives" into "liv").
  2. "one" is only read as the number 1 before a unit or inside a range ("one to two weeks"),
     so the pronoun in "died of one" no longer creates a phantom number.
  3. Compound number words ("thirty one") become digits ("31").
"""

import re

ONES = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}

# "one" counts as the number 1 when the next word is one of these.
UNIT_WORDS = {
    "day", "days", "week", "weeks", "month", "months", "year", "years", "hour", "hours",
    "minute", "minutes", "time", "times", "tablet", "tablets", "pill", "pills", "capsule",
    "capsules", "dose", "doses", "mg", "ml", "cigarette", "cigarettes", "unit", "units",
    "drink", "drinks", "pack", "packs", "episode", "episodes",
}
RANGE_LINKS = {"to", "or"}

NEGATION_CUES = {
    "no", "not", "denies", "denied", "deny", "denying", "without", "never", "none", "negative",
    "nothing", "inability", "unable", "against", "cannot", "cant", "avoid",
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "has", "have", "had", "was", "were", "are",
    "his", "her", "she", "him", "from", "into", "than", "then", "also", "will", "been",
    "patient", "reports", "reported", "states", "stated", "noted", "presents", "presenting",
    "history", "doctor", "clinician", "plan", "per",
}

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def _is_number_word(tok: str | None) -> bool:
    return tok is not None and (tok in ONES or tok in TEENS or tok in TENS or tok == "one" or bool(_DIGITS.fullmatch(tok)))


def _convert_numbers(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]
        nxt = tokens[i + 1] if i + 1 < n else None
        after = tokens[i + 2] if i + 2 < n else None
        if tok in TENS:
            if nxt == "one" or nxt in ONES:
                out.append(str(TENS[tok] + (1 if nxt == "one" else ONES[nxt])))
                i += 2
                continue
            out.append(str(TENS[tok]))
        elif tok in TEENS:
            out.append(str(TEENS[tok]))
        elif tok in ONES:
            out.append(str(ONES[tok]))
        elif tok == "one":
            is_unit = nxt in UNIT_WORDS
            is_range = nxt in RANGE_LINKS and _is_number_word(after)
            out.append("1" if (is_unit or is_range) else "one")
        else:
            out.append(tok)
        i += 1
    return out


def normalize(text: str) -> str:
    text = text.lower().replace("\u2019", "'")
    text = re.sub(r"n't\b", " not", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # drop periods, keep decimals
    text = re.sub(r"[^a-z0-9.\s]", " ", text)
    return " ".join(_convert_numbers(text.split()))


def stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        tok = tok[:-3] + "y"
    elif len(tok) > 4 and tok.endswith(("sses", "xes", "zes", "ches", "shes")):
        tok = tok[:-2]
    elif len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        tok = tok[:-1]
    for suffix in ("ing", "ed"):
        if tok.endswith(suffix) and len(tok) - len(suffix) >= 3:
            tok = tok[: -len(suffix)]
            break
    if len(tok) > 3 and tok.endswith("e"):
        tok = tok[:-1]
    if len(tok) > 3 and tok[-1] == tok[-2] and tok[-1] not in "sl":
        tok = tok[:-1]  # "stopped" and "stopping" both become "stop"
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
