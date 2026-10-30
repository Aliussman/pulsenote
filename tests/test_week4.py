import json

from eval.keyfacts import compute_recall, fact_recalled, load_key_facts
from eval.run_eval import build_review_sample, run
from eval.score_labels import score
from eval.stats import wilson
from tests.test_eval import ENCOUNTERS, fake_llm

FACTS = load_key_facts("data/key_facts.example.jsonl")["enc_001"]


def fact(label):
    return next(f for f in FACTS if f["label"] == label)


def test_fact_matches_with_number_words():
    assert fact_recalled(fact("cough for 2 weeks"), ["Patient has had a cough for two weeks."])


def test_negation_required_fact_rejects_positive_sentence():
    assert not fact_recalled(fact("no fever"), ["Patient reports fever."])
    assert fact_recalled(fact("no fever"), ["Patient denies fever."])


def test_missing_fact_is_not_recalled():
    assert not fact_recalled(fact("inhaler prescribed"), ["Patient has a cough."])


def test_recall_variants_from_fake_run():
    rows, _, _ = run(ENCOUNTERS, fake_llm)
    result = compute_recall(rows, {"enc_001": FACTS})
    assert result["baseline"]["total"] == 5
    assert result["grounded_all"]["recalled"] >= result["grounded_unflagged"]["recalled"]
    assert result["grounded_all"]["encounters_scored"] == 1


def test_wilson_bounds():
    lo, hi = wilson(5, 20)
    assert 0 <= lo < 0.25 < hi <= 1
    assert wilson(0, 0) == (0.0, 0.0)


def test_score_labels_confusion():
    rows, _, _ = run(ENCOUNTERS, fake_llm)
    review, key = build_review_sample(rows, per_system=5)
    labels = []
    for item in review:
        info = key[item["item_id"]]
        # Pretend a human agreed with the automated flag every time.
        labels.append({**item, "human_label": "unsupported" if info["flagged"] else "supported"})
    summary = score(labels, key)
    assert set(summary) == {"baseline", "grounded"}
    for s in summary.values():
        assert s["automated_check"].get("missed_unsupported", 0) == 0
        assert s["automated_check"].get("flagged_but_supported", 0) == 0
