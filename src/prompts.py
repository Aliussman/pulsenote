import json

from .schemas import RawNote, Turn

SYSTEM_PROMPT = """You are a clinical documentation assistant. You convert a transcript of a \
doctor-patient conversation into a SOAP note.

The transcript is split into numbered turns like [T3] Doctor: ... Every claim in your note \
must be traceable to those turns.

Hard rules:
1. Use only information that is stated in the transcript. Never add diagnoses, medications, \
doses, test results, or plans that nobody said.
2. Write one atomic claim per sentence. If a sentence contains two facts, split it.
3. Every sentence must cite at least one turn. For each citation give the turn_id (an integer, \
so 3 for [T3]) and a short \
quote (at most 15 words) copied exactly from that turn, character for character.
4. If you cannot support a sentence with an exact quote, leave the sentence out.
5. Keep negations and uncertainty exactly as spoken. "No fever" must never become "fever". \
"Possibly" or "might be" must stay hedged.
6. Copy numbers, doses, units and durations exactly as stated.
7. Sections:
   S (Subjective): what the patient reports, including symptoms, history, medications, allergies.
   O (Objective): exam findings, vitals and results that someone says out loud in the transcript.
   A (Assessment): the clinician's stated impressions or diagnoses only. Do not diagnose yourself.
   P (Plan): what the clinician says will be done, such as prescriptions, tests, referrals, follow-up.
8. If the transcript has nothing for a section, write no sentences for that section. Do not \
write filler such as "not documented".
9. Output valid JSON that matches the schema below and nothing else. No markdown fences.

JSON schema:
{schema}
"""


def build_system_prompt() -> str:
    schema = json.dumps(RawNote.model_json_schema(), indent=2)
    return SYSTEM_PROMPT.replace("{schema}", schema)


def format_transcript(turns: list[Turn]) -> str:
    return "\n".join(f"[T{t.id}] {t.speaker}: {t.text}" for t in turns)


def build_user_prompt(turns: list[Turn], previous_error: str | None = None) -> str:
    prompt = "Transcript:\n" + format_transcript(turns) + "\n\nWrite the SOAP note as JSON."
    if previous_error:
        prompt += (
            "\n\nYour previous answer could not be parsed. Fix this problem and answer again:\n"
            + previous_error
        )
    return prompt
