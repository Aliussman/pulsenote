from src.grounding import validate_sentence
from src.schemas import RawSentence, Support, Turn

TURNS = [
    Turn(id=1, speaker="Doctor", text="What brings you in today?"),
    Turn(id=2, speaker="Patient", text="I've had a cough for two weeks, but no fever."),
    Turn(id=3, speaker="Doctor", text="It sounds like bronchitis. I'll prescribe an inhaler and see you in 10 days."),
]
BY_ID = {t.id: t for t in TURNS}


def sentence(text, section, turn_id, quote):
    return RawSentence(text=text, section=section, support=[Support(turn_id=turn_id, quote=quote)])


def reasons(s):
    return validate_sentence(s, BY_ID)


def test_supported_sentence_passes():
    s = sentence("Patient reports cough for 2 weeks.", "S", 2, "a cough for two weeks")
    assert reasons(s) == []


def test_invented_number_is_flagged():
    s = sentence("Patient reports cough for 3 weeks.", "S", 2, "a cough for two weeks")
    assert any(r.startswith("numbers_not_in_source") for r in reasons(s))


def test_dropped_negation_is_flagged():
    s = sentence("Patient reports fever.", "S", 2, "no fever")
    assert "possible_dropped_negation" in reasons(s)


def test_fabricated_quote_is_flagged():
    s = sentence("Patient reports shortness of breath.", "S", 2, "shortness of breath")
    assert any(r.startswith("quote_not_in_turn") for r in reasons(s))


def test_unknown_turn_is_flagged():
    s = sentence("Patient reports cough.", "S", 99, "a cough")
    assert any(r.startswith("unknown_turn") for r in reasons(s))


def test_no_support_is_flagged():
    s = RawSentence(text="Patient has asthma.", section="S", support=[])
    assert reasons(s) == ["no_support"]


def test_assessment_from_patient_turn_is_flagged():
    s = sentence("Assessment is a cough lasting two weeks.", "A", 2, "a cough for two weeks")
    assert "assessment_or_plan_not_from_clinician" in reasons(s)


def test_assessment_from_clinician_passes():
    s = sentence("Likely bronchitis.", "A", 3, "sounds like bronchitis")
    assert reasons(s) == []


def test_plan_with_correct_follow_up_passes():
    s = sentence("Follow up in 10 days.", "P", 3, "see you in 10 days")
    assert reasons(s) == []
