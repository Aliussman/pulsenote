from src.posthoc import expand_qa, post_hoc_check
from src.schemas import Turn
from src.textnorm import content_words, has_negation, normalize, numbers, stem


# 1. stemmer
def test_live_forms_share_a_stem():
    assert stem("lives") == stem("live") == stem("living") == stem("lived")


def test_other_stems_still_sensible():
    assert stem("weeks") == stem("week")
    assert stem("stopped") == stem("stopping") == stem("stop")
    assert stem("rashes") == stem("rash")
    assert stem("bronchitis") == "bronchitis"


def test_lives_alone_matches_live_on_my_own():
    turns = [Turn(id=1, speaker="Doctor", text="Who do you live with?"), Turn(id=2, speaker="Patient", text="Um, I live on my own.")]
    reasons = post_hoc_check("The patient lives alone.", "S", turns)
    assert "no_matching_turn" not in reasons


# 2. the pronoun "one"
def test_pronoun_one_is_not_a_number():
    assert numbers("Her mother died of one.") == set()
    assert numbers("One of them is worse.") == set()


def test_one_before_a_unit_or_in_a_range_is_a_number():
    assert numbers("one week") == {"1"}
    assert numbers("one to two weeks") == {"1", "2"}
    assert numbers("one or two tablets") == {"1", "2"}


def test_compound_number_words():
    assert normalize("you know I'm thirty one") .endswith("31")
    assert numbers("Thirty-one years old") == {"31"}
    assert numbers("about twenty") == {"20"}
    assert numbers("six or seven times a day") == {"6", "7"}


# negation cues from the audit
def test_negation_cues_from_the_audit():
    assert has_negation("The doctor advises against antibiotics")
    assert has_negation("an inability to sleep")
    assert has_negation("I can't focus")
    assert not has_negation("I can focus well")


# 3. post-hoc Q&A rule
SMOKING = [
    Turn(id=1, speaker="Doctor", text="Do you smoke at all, and do you drink alcohol?"),
    Turn(id=2, speaker="Patient", text="No."),
    Turn(id=3, speaker="Doctor", text="Okay, any family history of brain cancer?"),
    Turn(id=4, speaker="Patient", text="No."),
]


def test_expand_qa_adds_the_one_word_answer():
    ids = [t.id for t in expand_qa([SMOKING[0]], SMOKING)]
    assert ids == [1, 2]


def test_one_word_no_answer_is_found_for_a_denial():
    reasons = post_hoc_check("The patient denies smoking and alcohol consumption.", "S", SMOKING)
    assert "negation_not_in_source" not in reasons


def test_invented_negation_is_still_caught():
    turns = [Turn(id=1, speaker="Doctor", text="Any fever?"), Turn(id=2, speaker="Patient", text="Yes, since Monday.")]
    assert "negation_not_in_source" in post_hoc_check("The patient denies fever.", "S", turns)


# audit finding: clinician turns first for A and P
PRESCRIBE = [
    Turn(id=1, speaker="Patient", text="The cream I have is not helping, I need a stronger cream."),
    Turn(id=2, speaker="Patient", text="I put the cream on twice a day."),
    Turn(id=3, speaker="Doctor", text="I will prescribe a stronger steroid cream for you."),
]


def test_plan_matches_the_clinician_turn_not_the_patient_turn():
    reasons = post_hoc_check("Prescribe a stronger steroid cream.", "P", PRESCRIBE)
    assert "assessment_or_plan_not_from_clinician" not in reasons


def test_plan_only_said_by_the_patient_is_still_flagged():
    turns = [
        Turn(id=1, speaker="Doctor", text="How are you feeling?"),
        Turn(id=2, speaker="Patient", text="I think I need antibiotics for this."),
    ]
    assert "assessment_or_plan_not_from_clinician" in post_hoc_check("Prescribe antibiotics.", "P", turns)


# audit finding: numbers said far from the symptom
AGE = [
    Turn(id=1, speaker="Doctor", text="How old are you?"),
    Turn(id=2, speaker="Patient", text="I'm thirty one."),
    Turn(id=3, speaker="Doctor", text="Okay, what has been going on with your skin?"),
    Turn(id=4, speaker="Patient", text="I have a sore red rash on my arms for four days."),
]


def test_number_said_in_a_distant_turn_is_accepted():
    reasons = post_hoc_check("The patient is 31 years old with a sore red rash for 4 days.", "S", AGE)
    assert not any(r.startswith("numbers_not_in_source") for r in reasons)


def test_number_that_appears_nowhere_is_still_flagged():
    reasons = post_hoc_check("The patient has had a sore red rash for 9 days.", "S", AGE)
    assert any(r.startswith("numbers_not_in_source") for r in reasons)


def test_content_words_are_unchanged_for_plain_text():
    assert content_words("Patient reports cough for two weeks") == {"cough", "week"}
