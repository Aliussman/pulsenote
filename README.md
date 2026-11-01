# PulseNote

> **Citation-grounded clinical SOAP note generation with an automated and human-in-the-loop evaluation harness.**

PulseNote converts doctor-patient dialogue transcripts into structured SOAP (Subjective, Objective, Assessment, Plan) notes where every sentence carries exact quote citations back to the transcript. It couples this with a deterministic verification engine and a rigorous evaluation harness that benchmarks citation-enforced generation against standard prompting.

---

## Key Highlights

- **Atomic Citation Provenance:** The LLM is forced to output one atomic claim per sentence, each citing the exact turn ID and an exact verbatim quote ($\le 15$ words).
- **Deterministic Heuristic Validator:** Catches common LLM failure modes without external model calls:
  - **Quote Verification:** Fuzzy matches quotes against cited turns (`SequenceMatcher` ratio $\ge 0.9$).
  - **Quantity & Dose Consistency:** Extracts all numbers, dosages, and durations, ensuring they exist in the source turn.
  - **Negation Consistency:** Flags dropped negations (e.g., turning *"no fever"* into *"fever"*) and hallucinated negations.
  - **Lexical Overlap:** Stemmed content-word overlap checks with section-specific thresholds.
  - **Clinical Authority:** Enforces that Assessment (**A**) and Plan (**P**) statements cite clinician turns rather than patient statements.
- **Fair Baseline Comparison:** A post-hoc lexical turn matcher scores ungrounded baseline notes under the exact same verification criteria.
- **End-to-End Evaluation Suite:**
  - Automated latency, pass rate, and flag distribution logging.
  - Interactive terminal CLI for **blind human review** with randomized item IDs.
  - Statistical scoring with **95% Wilson score confidence intervals**.
  - **Key-fact clinical recall** scored against gold standard clinical facts.
- **Multi-Provider Support:** Supports both **Google Gemini API** (free tier with `gemini-3.8-flash` or `gemini-3.5-flash-lite`) and **Anthropic Claude API** (`claude-3-5-sonnet-20241022`).

---

## How It Works

```
                         Doctor-Patient Transcript
                       [T1] Doctor: ...  [T2] Patient: ...
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
      Grounded Pipeline (src/pipeline.py)      Baseline Pipeline (src/baseline.py)
      - Atomic claims with quote citations     - 1 fact / sentence
      - JSON schema enforcement                - No citations required
                 │                                       │
                 ▼                                       ▼
      Deterministic Validator (src/grounding.py) Post-Hoc Alignment (src/posthoc.py)
      - Quote fidelity                         - Top-k turn retrieval
      - Quantities, durations & dosages        - Number & negation checks
      - Dropped/hallucinated negations         - Clinician speaker check
      - Clinician speaker authority (A & P)              │
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     ▼
                          Evaluation Harness (eval/)
                          ├── Automated Runner (run_eval.py)
                          ├── Blind Labeling CLI (label.py)
                          ├── 95% Wilson CI Scorer (score_labels.py)
                          └── Key-Fact Recall (score_keyfacts.py)
```

---

## Quickstart

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/Aliussman/pulsenote.git
cd pulsenote

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run unit tests (uses deterministic mock LLM; no API key required)
pytest -v
```

### 2. Dataset Preparation (PriMock57)

The repository includes a download and conversion script for the **PriMock57** dataset (57 simulated primary care consultations from Babylon Health / Hugging Face):

```bash
# Downloads and formats all 57 encounters into data/encounters.jsonl
python scripts/download_and_convert_primock57.py
```

This generates:
- `data/encounters.jsonl`: 57 standardized multi-turn consultations with normalized speaker roles (`Doctor` / `Patient`).
- `data/reference_notes.json`: Clinician-authored reference notes and clinical highlights.

---

## Running the Evaluation

### Option A: Google Gemini API (Recommended & Free Tier)

Get a free API key from [Google AI Studio](https://aistudio.google.com/):

```bash
export GEMINI_API_KEY="your-gemini-api-key"
export PULSENOTE_MODEL="gemini-3.8-flash"   # or gemini-3.5-flash-lite

# Run evaluation on 10 encounters
python -m eval.run_eval --data data/encounters.jsonl --n 10 --out results/
```

### Option B: Anthropic Claude API

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
export PULSENOTE_MODEL="claude-3-5-sonnet-20241022"

python -m eval.run_eval --data data/encounters.jsonl --n 10 --provider anthropic --out results/
```

Evaluation outputs saved to `results/`:
- `results/per_sentence.jsonl`: Sentence-level check logs, citation quotes, and validation flags.
- `results/summary.json`: Pass rates, latency breakdown (mean, median, max), and flag type frequencies.
- `results/review_sample.jsonl`: Blinded sample for human annotation.
- `results/review_key.json`: De-identified mapping between review items and systems/checks.

---

## Human Review & Scoring

### 1. Blind Hand Labeling

Launch the interactive labeling tool in your terminal:

```bash
python -m eval.label --data data/encounters.jsonl
```

- Displays the transcript alongside generated sentences without revealing which system generated them.
- Label sentences as `s` (supported), `u` (unsupported), or `c` (unclear).
- State-persisted and resumable at any time.

### 2. Score Human Labels (with 95% Confidence Intervals)

```bash
python -m eval.score_labels
```

Computes unsupported-sentence rates per system using the **Wilson score interval** (safer for smaller sample sizes), and generates a confusion matrix evaluating how reliably the automated validator flagged unsupported sentences.

### 3. Score Key-Fact Recall

```bash
python -m eval.score_keyfacts --facts data/key_facts.jsonl
```

Measures clinical completeness across three variants:
1. `baseline`: Standard ungrounded notes.
2. `grounded_all`: All citation-grounded sentences.
3. `grounded_unflagged`: Only sentences that passed all deterministic validation checks (the clinical trust threshold).

---

## Repository Structure

```
pulsenote/
├── data/
│   ├── encounters.example.jsonl     # Sample schema for encounters
│   ├── encounters.jsonl             # Full converted PriMock57 dataset (57 encounters)
│   ├── key_facts.example.jsonl      # Sample schema for gold key facts
│   ├── key_facts.jsonl              # Gold key facts for recall scoring
│   └── reference_notes.json         # Clinician reference notes & highlights
├── eval/
│   ├── keyfacts.py                  # Term and negation matching for fact recall
│   ├── label.py                     # Blind terminal labeling CLI
│   ├── metrics.py                   # Aggregation, summaries, and table formatting
│   ├── run_eval.py                  # Evaluation orchestrator
│   ├── score_keyfacts.py            # CLI runner for fact recall scoring
│   ├── score_labels.py              # CLI runner for human label scoring
│   └── stats.py                     # Wilson score interval calculation
├── scripts/
│   └── download_and_convert_primock57.py  # PriMock57 downloader & converter
├── src/
│   ├── baseline.py                  # Ungrounded comparison pipeline
│   ├── grounding.py                 # Deterministic heuristic validator
│   ├── llm.py                       # Unified wrapper for Gemini & Anthropic APIs
│   ├── pipeline.py                  # Citation-grounded note generator
│   ├── posthoc.py                   # Post-hoc lexical alignment for fair comparison
│   ├── prompts.py                   # System & user prompt templates
│   └── schemas.py                   # Pydantic data models
├── tests/
│   ├── test_eval.py                 # Tests for metrics and post-hoc checks
│   ├── test_grounding.py            # Unit tests for deterministic validation rules
│   └── test_week4.py                # Tests for key-fact matching and Wilson CI
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Limitations & Disclaimer

- **Simulated Consultations:** This benchmark uses simulated consultations (PriMock57). Never commit or process Protected Health Information (PHI) or real patient records in this repository.
- **Heuristic Scope:** The deterministic checks catch common discrepancies (invented numbers, dropped negations, fake quotes, wrong speaker), but cannot replace comprehensive clinical review.
- **Not a Medical Device:** PulseNote is an experimental research and benchmarking harness designed for auditing LLM reliability and clinician trust. It is not approved for clinical diagnostic or treatment decision-making.
