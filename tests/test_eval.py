import json

from eval.metrics import format_table, summarize
from eval.run_eval import build_review_sample, run
from src.posthoc import post_hoc_check
from src.schemas import Turn

TURNS = [
    Turn(id=1, speaker="Doctor", text="What brings you in today?"),
    Turn(id=2, speaker="Patient", text="I've had a cough for two weeks, but no fever."),
    Turn(id=3, speaker="Doctor", text="It sounds like bronchitis. I'll prescribe an inhaler and see you in 10 days."),
]
ENCOUNTERS = [{"id": "enc_001", "turns": [t.model_dump() for t in TURNS]}]


def fake_llm(system: str, user: str) -> str:
    if "Hard rules" in system:  # grounded pipeline
        return json.dumps(
            {
                "sentences": [
                    {
                        "text": "Patient reports cough for 2 weeks.",
                        "section": "S",
                        "support": [{"turn_id": 2, "quote": "a cough for two weeks"}],
                    },
                    {
                        "text": "Patient reports fever.",
                        "section": "S",
                        "support": [{"turn_id": 2, "quote": "no fever"}],
                    },
                ]
            }
        )
    return json.dumps(  # baseline
        {
            "sentences": [
                {"text": "Patient has had a cough for 2 weeks.", "section": "S"},
                {"text": "Patient has had a cough for 5 weeks.", "section": "S"},
            ]
        }
    )


def test_posthoc_passes_supported_sentence():
    assert post_hoc_check("Patient has a cough for 2 weeks.", "S", TURNS) == []


def test_posthoc_flags_invented_number():
    reasons = post_hoc_check("Patient has a cough for 5 weeks.", "S", TURNS)
    assert any(r.startswith("numbers_not_in_source") for r in reasons)


def test_posthoc_flags_text_with_no_match():
    assert post_hoc_check("Patient takes metformin.", "S", TURNS) == ["no_matching_turn"]


def test_end_to_end_with_fake_model():
    rows, latencies, failures = run(ENCOUNTERS, fake_llm)
    summary = summarize(rows, latencies, failures)

    assert failures == {"baseline": 0, "grounded": 0}
    assert summary["checks"]["baseline/posthoc"]["sentences"] == 2
    assert summary["checks"]["baseline/posthoc"]["passed"] == 1
    assert summary["checks"]["grounded/citation"]["passed"] == 1  # the dropped negation is caught
    assert "possible_dropped_negation" in summary["checks"]["grounded/citation"]["flag_reasons"]
    assert "baseline/posthoc" in format_table(summary)


def test_review_sample_is_blind():
    rows, _, _ = run(ENCOUNTERS, fake_llm)
    review, key = build_review_sample(rows, per_system=5)
    assert len(review) == len(key) == 4
    assert all("system" not in item for item in review)
