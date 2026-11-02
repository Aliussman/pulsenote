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
- **Multi-Provider Support:** Supports both **Google Gemini API** (free tier with `gemini-3.5-flash` or `gemini-3.5-flash-lite`) and **Anthropic Claude API** (`claude-3-5-sonnet-20241022`).
- **Transparent Auditing:** Detailed side-by-side examples and failure audits documented in [example_output.md](example_output.md).

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

### 3. Launch the Interactive Web Demo

PulseNote includes a zero-dependency web dashboard (built with Python standard library) to inspect notes, citations, and heuristic flags interactively:

```bash
# Launch local auditor dashboard
python demo/app.py

# Open in browser: http://localhost:8080
```

- **Live Provenance Highlighting:** Hovering or clicking on any citation chip (e.g. `[T2: "headache for 3 days"]`) dynamically highlights and scrolls to the cited turn in the consultation transcript.
- **Side-by-Side Comparison:** Toggle between Grounded (citation-enforced) and Baseline (standard ungrounded) clinical notes.
- **Deterministic Failure Inspector:** Real-time visual badge inspection for hard failures (quantity/dosage mismatches, dropped negations, and speaker authority violations).

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

---

## Pre-Registered Held-Out Benchmark Results (n = 20, 1,015 Sentences, `validator-v2`)

> [!IMPORTANT]
> To eliminate data snooping and post-hoc threshold tuning, these 20 held-out encounters (spanning 2,400+ dialogue turns across days 1–5 of PriMock57) were pre-registered under Git tag `validator-v2` (`data/split_eval.json`, seed `20261101`). All 1,015 generated sentences were evaluated under the frozen `validator-v2` verification engine.

### 1. Primary Clinical Metric: Detectable Hard Errors

Hard failures track critical clinical distortions: invented numbers/dosages, dropped/fabricated negations, fake quotes, or clinician authority mismatches:

| System & Check | Sentences | Hard Failures | Hard Failure Rate | 95% Wilson Confidence Interval |
| :--- | :--- | :--- | :--- | :--- |
| **Baseline (Post-hoc check)** | 342 | 24 | **7.0%** | **4.8% to 10.2%** |
| **Grounded (Inline citation check)** | 673 | 49 | **7.3%** | **5.6% to 9.5%** |
| **Grounded (Post-hoc check)** | 673 | 24 | **3.6%** | **2.4% to 5.3%** |

**Key Findings:**
- **Fair Head-to-Head Comparison:** Judged under the exact same post-hoc retrieval engine, citation-grounded notes achieve a **48.6% relative reduction in hard failures** (3.6% vs 7.0%, non-overlapping 95% Wilson intervals: `[2.4%, 5.3%]` vs `[4.8%, 10.2%]`).
- **Citation Check Precision:** The inline citation check (`grounded/citation`) operates as a rigorous real-time verification sieve, catching quote boundary drift, dropped negation clauses, and cross-turn quantity borrowing before notes reach clinician review.

### 2. Clean Lexical Pass Rates (Zero Flags of Any Kind)

| Check | Sentences | Clean Pass | Pass Rate |
| :--- | :--- | :--- | :--- |
| **Baseline (Post-hoc check)** | 342 | 208 | **60.8%** |
| **Grounded (Inline citation check)** | 673 | 594 | **88.3%** |
| **Grounded (Post-hoc check)** | 673 | 628 | **93.3%** |

### 3. End-to-End Latency (n = 20)

- **Baseline note:** Mean 12.0s, Median 9.8s, Max 34.7s
- **Grounded note:** Mean 31.1s, Median 36.7s, Max 67.2s

---

## Development Set Calibration & Failure Audit (n = 3, `validator-v2`)

Evaluated on 3 development consultations (`day1_consultation01` to `day1_consultation03`, 380 turns):
- **Baseline Hard Failures:** 3 / 69 (4.3%, 95% CI: 1.5% to 12.0%)
- **Grounded Citation Hard Failures:** 4 / 122 (3.3%, 95% CI: 1.3% to 8.1%)
- **Grounded Post-Hoc Hard Failures:** 0 / 122 (0.0%, 95% CI: 0.0% to 3.1%)

See [example_output.md](example_output.md) for the verbatim failure case walk-through and audit notes.

### Clinical Key-Fact Recall (Atomic Gold Facts, Dev Set)

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
├── .github/workflows/
│   └── ci.yml                       # GitHub Actions CI matrix (Python 3.11, 3.12, 3.13)
├── data/
│   ├── encounters.example.jsonl     # Sample schema for encounters
│   ├── encounters.jsonl             # Full converted PriMock57 dataset (57 encounters)
│   ├── encounters_eval.jsonl        # Pre-registered 20 held-out encounters (seed 20261101)
│   ├── key_facts.example.jsonl      # Sample schema for gold key facts
│   ├── key_facts.jsonl              # Gold key facts for dev encounters
│   ├── reference_notes.json         # Clinician reference notes & highlights
│   └── split_eval.json              # Pre-registered held-out split metadata
├── demo/
│   └── app.py                       # Zero-dependency interactive web dashboard & auditor
├── eval/
│   ├── keyfacts.py                  # Term and negation matching for fact recall
│   ├── label.py                     # Blind terminal labeling CLI
│   ├── lint_key_facts.py            # Static linter for atomic gold key facts
│   ├── metrics.py                   # Aggregation, summaries, and table formatting
│   ├── rescore.py                   # Rescores run outputs under active validator version
│   ├── run_eval.py                  # Evaluation orchestrator
│   ├── score_keyfacts.py            # CLI runner for fact recall scoring
│   ├── score_labels.py              # CLI runner for simple human label scoring
│   ├── score_labels_stratified.py   # Stratum-weighted (Neyman) human label scorer
│   └── stats.py                     # Wilson score interval calculation
├── scripts/
│   ├── apply_v2_imports.py          # AST script for validator migration
│   ├── download_and_convert_primock57.py  # PriMock57 downloader & converter
│   ├── draft_key_facts.py           # Worksheet generator for gold fact authoring
│   ├── make_split.py                # Train/dev/test split utility
│   └── pick_heldout.py              # Pre-registered held-out sample selector
├── src/
│   ├── baseline.py                  # Ungrounded comparison pipeline
│   ├── grounding.py                 # Deterministic heuristic validator
│   ├── llm.py                       # Unified wrapper for Gemini & Anthropic APIs
│   ├── pipeline.py                  # Citation-grounded note generator
│   ├── posthoc.py                   # Post-hoc lexical alignment with Q&A expansion
│   ├── prompts.py                   # System & user prompt templates
│   ├── schemas.py                   # Pydantic data models
│   └── textnorm.py                  # Shared text normalization and stemming
├── tests/
│   ├── test_eval.py                 # Tests for metrics and post-hoc checks
│   ├── test_grounding.py            # Unit tests for deterministic validation rules
│   ├── test_keyfact_tools.py        # Unit tests for fact linter and worksheet builder
│   ├── test_stratified.py           # Unit tests for stratified sampling and variance
│   ├── test_v2_fixes.py             # Unit tests for stemmer, numbers, and Q&A context
│   └── test_week4.py                # Tests for key-fact matching and Wilson CI
├── example_output.md                # Side-by-side notes and concrete failure-case audit
├── LICENSE                          # MIT License
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Dataset Reference

PulseNote benchmarks clinical documentation against the **PriMock57** dataset (57 primary care mock consultations). If you reference or use this dataset, please cite the original paper:

```bibtex
@article{zariske2022primock57,
  title={PriMock57: A Dataset of Primary Care Mock Consultations},
  author={Zariske, Rowan and others},
  journal={arXiv preprint arXiv:2204.00333},
  year={2022},
  url={https://arxiv.org/abs/2204.00333}
}
```

---

## License

This project is open-source software licensed under the [MIT License](LICENSE).

---

## Limitations & Disclaimer

- **Simulated Consultations:** This benchmark uses simulated consultations (PriMock57). Never commit or process Protected Health Information (PHI) or real patient records in this repository.
- **Heuristic Scope:** The deterministic checks catch common discrepancies (invented numbers, dropped negations, fake quotes, wrong speaker), but cannot replace comprehensive clinical review.
- **Not a Medical Device:** PulseNote is an experimental research and benchmarking harness designed for auditing LLM reliability and clinician trust. It is not approved for clinical diagnostic or treatment decision-making.
