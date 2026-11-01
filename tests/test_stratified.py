import pytest

from eval.score_labels_stratified import format_report, score, stratum_of


def make_rows():
    """100 baseline sentences: 10 hard, 20 soft-only, 70 clean. Grounded is empty."""
    rows = []
    for i in range(100):
        hard = ["numbers_not_in_source:5"] if i < 10 else []
        soft = ["low_overlap:0.30"] if 10 <= i < 30 else []
        rows.append(
            {
                "system": "baseline",
                "check": "posthoc",
                "encounter_id": f"enc_{i % 5}",
                "text": f"sentence {i}",
                "hard_reasons": hard,
                "soft_reasons": soft,
            }
        )
    return rows


def make_labels(rows):
    """Sample 5 hard (4 unsupported), 5 soft (1 unsupported), 10 clean (1 unsupported)."""
    plan = [(0, 5, 4), (10, 15, 1), (30, 40, 1)]
    labels, key = [], {}
    n = 0
    for start, stop, bad in plan:
        for j, i in enumerate(range(start, stop)):
            item_id = f"item_{n:03d}"
            n += 1
            key[item_id] = {"system": "baseline"}
            labels.append(
                {
                    "item_id": item_id,
                    "encounter_id": rows[i]["encounter_id"],
                    "text": rows[i]["text"],
                    "human_label": "unsupported" if j < bad else "supported",
                }
            )
    return labels, key


def test_stratum_assignment():
    r = make_rows()
    assert stratum_of(r[0]) == "hard" and stratum_of(r[15]) == "soft" and stratum_of(r[50]) == "clean"


def test_weighted_rate_corrects_the_oversampling():
    rows = make_rows()
    labels, key = make_labels(rows)
    out = score(labels, key, rows, boot=300)["baseline"]
    # Unweighted would be 6 / 20 = 30%. Weighted: (10*0.8 + 20*0.2 + 70*0.1) / 100 = 19%.
    assert out["weighted_unsupported_rate"] == pytest.approx(0.19)
    assert out["share_of_unsupported_that_was_hard_flagged"] == pytest.approx(8 / 19)
    assert out["share_of_unsupported_that_had_any_flag"] == pytest.approx(12 / 19)
    assert out["population"] == {"hard": 10, "soft": 20, "clean": 70}
    lo, hi = out["weighted_unsupported_rate_95ci"]
    assert lo <= 0.19 <= hi


def test_unclear_bounds_bracket_the_estimate():
    rows = make_rows()
    labels, key = make_labels(rows)
    labels[7]["human_label"] = "unclear"
    labels[12]["human_label"] = "unclear"
    out = score(labels, key, rows, boot=100)["baseline"]
    assert out["unclear_bounds"]["lower"] <= out["weighted_unsupported_rate"] <= out["unclear_bounds"]["upper"]


def test_missing_stratum_is_reported_not_guessed():
    rows = make_rows()
    labels, key = make_labels(rows)
    labels = [l for l in labels if not (l["text"].startswith("sentence ") and int(l["text"].split()[1]) >= 30)]
    out = score(labels, key, rows, boot=50)["baseline"]
    assert "error" in out and "clean" in out["error"]


def test_labels_missing_from_rows_are_counted_and_skipped():
    rows = make_rows()
    labels, key = make_labels(rows)
    labels[0]["text"] = "a sentence that is not in the rows"
    result = score(labels, key, rows, boot=50)
    assert result["unmatched_labels"] == {"baseline": 1}


def test_report_formats():
    rows = make_rows()
    labels, key = make_labels(rows)
    text = format_report(score(labels, key, rows, boot=50))
    assert "weighted unsupported rate" in text and "baseline" in text
