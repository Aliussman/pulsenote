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
export PULSENOTE_MODEL="gemini-3.5-flash"   # or gemini-3.5-flash-lite

# Run evaluation on encounters
python -m eval.run_eval --data data/encounters.jsonl --n 3 --out results/
```

### Option B: Anthropic Claude API

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
export PULSENOTE_MODEL="claude-3-5-sonnet-20241022"

python -m eval.run_eval --data data/encounters.jsonl --n 3 --provider anthropic --out results/
```

Evaluation outputs saved to `results/`:
- `results/per_sentence.jsonl`: Sentence-level check logs, citation quotes, and validation flags.
- `results/summary.json`: Pass rates, latency breakdown (mean, median, max), and flag type frequencies.
- `results/review_sample.jsonl`: Blinded sample for human annotation.
- `results/review_key.json`: De-identified mapping between review items and systems/checks.

---

## Automated Lexical Support & Citation Auditing (Development Set, n = 3, `validator-v2`)

> [!NOTE]
> The automated checks below use lexical overlap, exact quote matching, number extraction, and negation cues as a proxy for attribution. Under `validator-v2`, post-hoc checks expand adjacent question/answer turns and check numbers against document scope. They measure whether text aligns closely with cited turns, not ground-truth clinical judgment. Human-labeled unsupported-claim rates with stratum-weighted scoring will be reported once the held-out evaluation is complete.

Evaluated on the 3 development consultations (`day1_consultation01` to `day1_consultation03`, 380 dialogue turns) using `gemini-3.5-flash`:

### 1. Primary Clinical Metric: Detectable Hard Errors

Hard failures track critical clinical errors: invented numbers/dosages, dropped/fabricated negations, fake quotes, or clinician authority mismatches (excluding benign phrasing/overlap drift):

| System & Check | Sentences | Hard Failures | Hard Failure Rate | 95% Wilson Confidence Interval |
| :--- | :--- | :--- | :--- | :--- |
| **Baseline (Post-hoc check)** | 69 | 3 | **4.3%** | **1.5% to 12.0%** |
| **Grounded (Inline citation check)** | 122 | 4 | **3.3%** | **1.3% to 8.1%** |
| **Grounded (Post-hoc check)** | 122 | 0 | **0.0%** | **0.0% to 3.1%** |

- **Baseline Hard Errors (3):** Includes 1 clear fabrication (`[O] Physical examination was deferred.`, never spoken in dialogue), 1 ungrounded prescription attribution, and 1 cross-turn duration mismatch.
- **Grounded Citation Errors (4):** 100% genuine attribution/quote boundaries caught by the inline checker (2 quote turn ID mismatches, 1 quote truncation dropping a negation, and 1 number duration imported from an uncited turn).

### 2. Clean Lexical Pass Rates (Zero Flags of Any Kind)

| Check | Sentences | Clean Pass | Pass Rate |
| :--- | :--- | :--- | :--- |
| **Baseline (Post-hoc check)** | 69 | 55 | **79.7%** |
| **Grounded (Inline citation check)** | 122 | 102 | **83.6%** |
| **Grounded (Post-hoc check)** | 122 | 118 | **96.7%** |

### 3. Clinical Key-Fact Recall (Atomic Gold Facts)

Scored against clinician-authored gold facts (`data/key_facts.jsonl`):

| Variant | Recalled / Total Facts | Recall Rate |
| :--- | :--- | :--- |
| **Baseline** | 14 / 16 | **87.5%** |
| **Grounded (All Sentences)** | 14 / 16 | **87.5%** |
| **Grounded (Unflagged Only)** | 14 / 16 | **87.5%** |

- **Diagnosis Recall:** 100.0% (3 / 3)
- **Plan Recall:** 80.0% (4 / 5)
- **Symptom Recall:** 87.5% (7 / 8)

### 4. End-to-End Latency

- **Baseline note (n=3):** Mean 11.5s, Median 11.5s, Max 11.9s
- **Grounded note (n=3):** Mean 41.4s, Median 41.4s, Max 48.6s

---

## Pre-Registered Held-Out Benchmark (n = 20 encounters)

To guarantee zero data snooping or post-hoc threshold tuning, 20 held-out encounters were pre-registered and committed under seed `20261101` in `data/split_eval.json`:
- `data/encounters_eval.jsonl` (20 encounters across days 1–5, 2,400+ dialogue turns).
- Key-facts authored from clinical reference notes prior to evaluation (`scripts/draft_key_facts.py` and `eval/lint_key_facts.py`).

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
