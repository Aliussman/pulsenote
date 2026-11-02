# PulseNote: Example Outputs & Failure-Case Audit

This document provides concrete side-by-side examples of generated clinical documentation, contrasting standard ungrounded prompting with PulseNote's citation-grounded architecture on consultation `day1_consultation01` from the [PriMock57 dataset](https://arxiv.org/abs/2204.00333).

It details how PulseNote's deterministic verification engine flags attribution failures, inventories real clinical hallucinations, and clarifies the trade-offs between automated lexical verification and human clinical review.

---

## 1. Dialogue Excerpt (`day1_consultation01`)

The consultation involves a patient presenting with headache and neck stiffness:

```text
[T1] Doctor: Good morning, how can I help you today?
[T2] Patient: Morning doctor. Um, I've got this headache and stiff neck that started about three days ago.
[T3] Doctor: Okay. Have you had any fever, vomiting, or sensitivity to light?
[T4] Patient: No, no fever, no vomiting. I don't think my eyes are sensitive.
...
[T63] Doctor: Have you been able to work or carry on normal activities?
[T64] Patient: I've been going to work. It's been tough, but I managed.
...
[T92] Doctor: Alright. I don't see any red flag signs of meningitis today, but we need to monitor it.
[T93] Doctor: In in three to four days, I'd like to come and see you again if it's not improving.
[T94] Doctor: Take paracetamol as needed, up to one gram every four to six hours.
[T95] Patient: Thank you doctor.
```

---

## 2. Generated Outputs Comparison

### Grounded Pipeline (`src/pipeline.py`)

In PulseNote's grounded pipeline, the LLM is constrained to output atomic claims where each sentence cites the exact turn ID and a verbatim transcript quote ($\le 15$ words).

#### Structured JSON Output
```json
{
  "subjective": [
    {
      "text": "The patient reports a headache and stiff neck starting three days ago.",
      "citations": [
        {"turn_id": 2, "quote": "headache and stiff neck that started about three days ago"}
      ]
    },
    {
      "text": "The patient denies fever, vomiting, and photophobia.",
      "citations": [
        {"turn_id": 4, "quote": "no fever, no vomiting. I don't think my eyes are sensitive"}
      ]
    },
    {
      "text": "The patient has continued going to work over the last three days.",
      "citations": [
        {"turn_id": 64, "quote": "I've been going to work."}
      ]
    }
  ],
  "objective": [],
  "assessment": [
    {
      "text": "The doctor notes no red flag signs of meningitis today.",
      "citations": [
        {"turn_id": 92, "quote": "I don't see any red flag signs of meningitis today"}
      ]
    }
  ],
  "plan": [
    {
      "text": "The clinician recommends paracetamol up to one gram every four to six hours as needed.",
      "citations": [
        {"turn_id": 94, "quote": "paracetamol as needed, up to one gram every four to six hours"}
      ]
    },
    {
      "text": "The doctor advises a follow-up visit if symptoms do not improve in three to four days.",
      "citations": [
        {"turn_id": 93, "quote": "in in three to four days, I'd like to come and see you again"}
      ]
    }
  ]
}
```

#### Rendered Clinical Note
> **Subjective:**
> - The patient reports a headache and stiff neck starting three days ago. `[T2: "headache and stiff neck that started about three days ago"]`
> - The patient denies fever, vomiting, and photophobia. `[T4: "no fever, no vomiting. I don't think my eyes are sensitive"]`
> - The patient has continued going to work over the last three days. `[T64: "I've been going to work."] [FLAGGED]`
>
> **Objective:**
> - *(None recorded)*
>
> **Assessment:**
> - The doctor notes no red flag signs of meningitis today. `[T92: "I don't see any red flag signs of meningitis today"]`
>
> **Plan:**
> - The clinician recommends paracetamol up to one gram every four to six hours as needed. `[T94: "paracetamol as needed, up to one gram every four to six hours"]`
> - The doctor advises a follow-up visit if symptoms do not improve in three to four days. `[T93: "in in three to four days, I'd like to come and see you again"] [FLAGGED]`

---

### Baseline Pipeline (`src/baseline.py`)

The ungrounded baseline uses standard prompting (one fact per sentence without citation constraints):

#### Rendered Clinical Note
> **Subjective:**
> - Patient presents with headache and stiff neck for the past 3 days.
> - Patient denies fever, nausea, vomiting, or visual disturbances.
> - Patient has been continuing to attend work despite discomfort.
>
> **Objective:**
> - Physical examination was deferred. `[FLAGGED]`
>
> **Assessment:**
> - Acute headache and neck stiffness, low clinical suspicion for acute meningitis.
>
> **Plan:**
> - Paracetamol 1g every 4-6 hours PRN.
> - Follow up in 3 to 4 days if symptoms fail to resolve or if red flag symptoms develop.

---

## 3. Deep Dive: Concrete Failure-Case Audits

### Case 1: Baseline Hallucination / Boilerplate Confabulation
- **System:** `baseline`
- **Section:** `[Objective]`
- **Sentence:** `"Physical examination was deferred."`
- **Checker:** Post-hoc alignment (`src/posthoc.py`)
- **Flags:** `['no_matching_turn']` (Hard Failure)
- **Clinical Root Cause:**
  This was an unprompted model fabrication. In virtual/telehealth consultations where no physical examination is conducted, standard LLMs frequently hallucinate standard electronic health record (EHR) boilerplate (e.g., *"Physical examination was deferred"* or *"Vitals normal"*). Because no turn in the transcript mentioned deferring an exam, the post-hoc alignment engine found zero supporting turns.

### Case 2: Cross-Turn Duration Hallucination Caught by Validator
- **System:** `grounded`
- **Section:** `[Subjective]`
- **Sentence:** `"The patient has continued going to work over the last three days."`
- **Citations:** `Turn 64: "I've been going to work."`
- **Checker:** Deterministic validator (`src/grounding.py`)
- **Flags:** `['numbers_not_in_source:3']` (Hard Failure)
- **Clinical Root Cause:**
  In Turn 64, the patient simply stated *"I've been going to work."* The number `"3"` (*"over the last three days"*) was spoken 62 turns earlier in Turn 2 (*"started about three days ago"*). The LLM merged information from disparate turns into a single atomic sentence without citing Turn 2. The deterministic validator detected that quantity `3` did not appear in cited Turn 64, successfully blocking an attribution provenance leak.

### Case 3: Negation Truncation / Asymmetric Quoting Caught by Validator
- **System:** `grounded`
- **Section:** `[Plan]`
- **Sentence:** `"The doctor advises a follow-up visit if symptoms do not improve in three to four days."`
- **Citations:** `Turn 93: "in in three to four days, I'd like to come and see you again."`
- **Checker:** Deterministic validator (`src/grounding.py`)
- **Flags:** `['negation_not_in_quote']` (Hard Failure)
- **Clinical Root Cause:**
  The generated sentence asserts a conditional negation (*"if symptoms do **not** improve"*). However, the quoted snippet (`"in in three to four days, I'd like to come and see you again"`) truncated the physician's speech and left out the condition (`"if it's not improving"`). The validator recognized that the sentence asserted a negation that was absent from the cited quotation text.

---

## 4. Key Takeaways from the Auditing Process

1. **Why Baseline Hard Failures Favor Grounded Notes:**
   Out of 14 initial post-hoc flags on baseline notes in the development set, an audit revealed that 13 were retriever limitations (e.g., failing to retrieve single-word `"No."` patient responses across turns or handling complex conversational paraphrasing). Only 1 was a true factual hallucination (`"Physical examination was deferred"`). Because grounded generation adheres closely to quoted wording, post-hoc matching finds cited text more readily. PulseNote explicitly reports this nuance rather than claiming an unweighted 4x hallucination reduction.

2. **The Role of the Deterministic Validator:**
   For grounded notes, 100% of hard failures caught by `src/grounding.py` were genuine model attribution errors (quote truncation, cross-turn number borrowing, or turn ID mismatches). The heuristic engine effectively screens citations without requiring an expensive secondary LLM judge.
