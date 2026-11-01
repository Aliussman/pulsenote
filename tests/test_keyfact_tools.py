import json
import subprocess
import sys

from eval.keyfacts import fact_recalled
from eval.lint_key_facts import lint

TURNS = [
    {"id": 1, "speaker": "Doctor", "text": "What brings you in?"},
    {"id": 2, "speaker": "Patient", "text": "My skin is itchy and I have had it for four days."},
    {"id": 3, "speaker": "Doctor", "text": "Any fever?"},
    {"id": 4, "speaker": "Patient", "text": "No."},
    {"id": 5, "speaker": "Doctor", "text": "In three to four days, I would like to see you again."},
]
TRANSCRIPTS = {"enc_001": TURNS}


def record(*facts):
    return [{"id": "enc_001", "facts": list(facts)}]


GOOD = [
    {"label": "itchy skin", "category": "symptom", "any_of": [["itch"]]},
    {"label": "duration 4 days", "category": "duration", "any_of": [["4 day"]]},
    {"label": "follow up in 3 to 4 days", "category": "followup", "any_of": [["see you again", "3"], ["follow up", "3"], ["review", "3"], ["come back", "3"], ["check up", "3"]]},
]


def test_atomic_facts_survive_a_split_note():
    # A model that splits the symptom and the duration into two sentences still scores both.
    note = ["The patient reports itchy skin.", "The symptoms started four days ago."]
    assert fact_recalled(GOOD[0], note) and fact_recalled(GOOD[1], note)


def test_follow_up_fact_matches_different_phrasings():
    assert fact_recalled(GOOD[2], ["Advised follow up in 3 days."])
    assert fact_recalled(GOOD[2], ["The doctor will review the patient in three days."])


def test_lint_accepts_a_clean_file():
    errors, _ = lint(record(*GOOD), TRANSCRIPTS)
    assert errors == []


def test_lint_rejects_a_fact_that_was_never_said():
    bad = {"label": "physical examination", "category": "exam", "any_of": [["examination"]]}
    errors, _ = lint(record(bad), TRANSCRIPTS)
    assert any("never appear" in e for e in errors)


def test_lint_rejects_an_unknown_category_and_bad_shape():
    errors, _ = lint(record({"label": "x", "category": "vibes", "any_of": [["itch"]]}, {"label": "y", "category": "symptom", "any_of": []}), TRANSCRIPTS)
    assert len(errors) >= 2


def test_lint_warns_about_compound_labels_and_missing_synonyms_and_negation():
    compound = {"label": "itchy skin and duration", "category": "symptom", "any_of": [["itch"]]}
    review_only = {"label": "review", "category": "followup", "any_of": [["see you again"]]}
    negative = {"label": "no fever", "category": "negative", "any_of": [["fever"]]}
    _, warnings = lint(record(compound, review_only, negative), TRANSCRIPTS)
    text = " ".join(warnings)
    assert "more than one fact" in text
    assert "also consider phrasings" in text
    assert "require_negation" in text


def test_pick_heldout_is_seeded_and_stays_inside_heldout(tmp_path):
    data = tmp_path / "enc.jsonl"
    data.write_text("\n".join(json.dumps({"id": f"enc_{i:02d}", "turns": []}) for i in range(30)) + "\n")
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"dev": ["enc_00", "enc_01", "enc_02"], "heldout": [f"enc_{i:02d}" for i in range(3, 30)]}))

    def run(tag):
        out_split, out_data = tmp_path / f"s_{tag}.json", tmp_path / f"d_{tag}.jsonl"
        subprocess.run(
            [sys.executable, "scripts/pick_heldout.py", "--data", str(data), "--split", str(split), "--n", "10",
             "--seed", "7", "--split-out", str(out_split), "--data-out", str(out_data)],
            check=True, capture_output=True,
        )
        return json.loads(out_split.read_text())["eval"], out_data

    first, out_data = run("a")
    second, _ = run("b")
    assert first == second and len(first) == 10
    assert not set(first) & {"enc_00", "enc_01", "enc_02"}
    assert len(out_data.read_text().strip().splitlines()) == 10


def test_draft_key_facts_writes_worksheet_and_skeleton(tmp_path):
    data = tmp_path / "enc.jsonl"
    data.write_text(json.dumps({"id": "enc_001", "turns": TURNS}) + "\n")
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({"enc_001": {"summary": "Itchy skin for 4 days."}}))
    ws, draft = tmp_path / "ws.md", tmp_path / "draft.jsonl"
    subprocess.run(
        [sys.executable, "scripts/draft_key_facts.py", "--data", str(data), "--notes", str(notes),
         "--worksheet", str(ws), "--draft", str(draft)],
        check=True, capture_output=True,
    )
    assert "[T2] Patient:" in ws.read_text() and "Itchy skin" in ws.read_text()
    assert json.loads(draft.read_text()) == {"id": "enc_001", "facts": []}
