# PulseNote

Citation-grounded SOAP note generation with an evaluation harness.
(Quick-start notes for development. Replace this with your real write-up later.)

## Setup

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # all tests use a fake model, no API key needed
```

## Run the evaluation

### Option A: Google Gemini API (Recommended & Free Tier)

Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/):

```bash
export GEMINI_API_KEY="your-gemini-api-key"
export PULSENOTE_MODEL="gemini-3.8-flash"   # or gemini-3.5-flash-lite
python -m eval.run_eval --data data/encounters.jsonl --n 10 --out results/
```

### Option B: Anthropic Claude API

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
export PULSENOTE_MODEL="claude-3-5-sonnet-20241022"
python -m eval.run_eval --data data/encounters.jsonl --n 10 --provider anthropic --out results/
```

Data format: one JSON object per line, see `data/encounters.example.jsonl`.
Never put real patient data in this repo.

## After the run

```
python -m eval.label --data data/encounters.jsonl        # blind hand labeling, resumable
python -m eval.score_labels                              # unsupported rate with 95% CI
python -m eval.score_keyfacts --facts data/key_facts.jsonl   # key-fact recall
```

Key facts format: see `data/key_facts.example.jsonl`.

## Layout

```
src/        prompts, schemas, grounding validator, pipeline, baseline, post-hoc check, LLM wrapper
eval/       runner, metrics, labeling tool, label scorer, key-fact recall, stats
tests/      pytest suite (fake model)
data/       your transcripts and key facts (examples included)
results/    generated outputs (git-ignored)
```
