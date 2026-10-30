"""The comparison system: a plain "just summarize it" SOAP note with no citations.

It deliberately uses the same output shape and the same one-fact-per-sentence rule as the
grounded pipeline, so the only real difference is the citation requirement.
"""

from pydantic import ValidationError

from .pipeline import LLMCall, _strip_fences
from .prompts import format_transcript
from .schemas import RawNote, Turn

BASELINE_SYSTEM_PROMPT = """Summarize the doctor-patient conversation into a SOAP note.

Sections: S (Subjective), O (Objective), A (Assessment), P (Plan).
Write one fact per sentence.
Output only JSON in this shape, with no markdown fences:
{"sentences": [{"text": "...", "section": "S"}]}
"""


def generate_baseline(turns: list[Turn], call_llm: LLMCall, max_retries: int = 1) -> RawNote:
    user = "Transcript:\n" + format_transcript(turns) + "\n\nWrite the SOAP note as JSON."
    error: str | None = None
    for _ in range(max_retries + 1):
        prompt = user if error is None else user + "\n\nFix this problem and answer again:\n" + error
        raw_text = call_llm(BASELINE_SYSTEM_PROMPT, prompt)
        try:
            return RawNote.model_validate_json(_strip_fences(raw_text))
        except ValidationError as e:
            error = str(e)[:1500]
    raise RuntimeError(f"Baseline output never matched the schema. Last error:\n{error}")
