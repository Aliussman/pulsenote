from typing import Callable

from pydantic import ValidationError

from .grounding import validate_note
from .prompts import build_system_prompt, build_user_prompt
from .schemas import RawNote, SOAPNote, Turn

# call_llm(system_prompt, user_prompt) -> raw text from the model.
# Wrap whichever provider you use so the pipeline stays provider-agnostic.
LLMCall = Callable[[str, str], str]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def generate_note(turns: list[Turn], call_llm: LLMCall, max_retries: int = 2) -> SOAPNote:
    system = build_system_prompt()
    error: str | None = None
    for _ in range(max_retries + 1):
        raw_text = call_llm(system, build_user_prompt(turns, previous_error=error))
        try:
            raw_note = RawNote.model_validate_json(_strip_fences(raw_text))
            return validate_note(raw_note, turns)
        except ValidationError as e:
            error = str(e)[:1500]
    raise RuntimeError(f"Model output never matched the schema. Last error:\n{error}")
