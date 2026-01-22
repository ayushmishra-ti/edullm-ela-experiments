---
name: ela-mcq-evaluation-criteria
description: Evaluation criteria and InceptBench format for Grade 3 ELA MCQ. Defines quality targets, pass thresholds, and input/output for InceptBench.
---

# ELA MCQ Evaluation Criteria Skill

This skill defines how to evaluate Grade 3 ELA MCQs: InceptBench input/output format, quality targets, and pass/fail thresholds. **Evaluation runs in Python (InceptBench API); this skill is the specification.** Skills run in a sandbox with no network, so the actual InceptBench call cannot run inside a Skill.

## Purpose

- Define InceptBench-compatible input for ELA MCQ items
- Define quality targets (aggregate score, pass rate)
- Interpret InceptBench scores (0–1 → 0–100, ACCEPTABLE/REVISE/REJECT)

---

## InceptBench Input Format

For each generated item, send:

```json
{
  "id": "l_3_1_e_mcq_easy_001",
  "curriculum": "common_core",
  "request": {
    "grade": "3",
    "subject": "ela",
    "type": "mcq",
    "difficulty": "easy",
    "locale": "en-US",
    "skills": {
      "lesson_title": "",
      "substandard_id": "CCSS.ELA-LITERACY.L.3.1.E",
      "substandard_description": "Form and use the simple verb tenses."
    },
    "instruction": ""
  },
  "content": "What is the question text? A) ... B) ... C) ... D) ..."
}
```

For structured `content`, InceptBench accepts the `content` object from generation (question, answer, answer_options, answer_explanation). When using the REST API with `generated_content`, use the full `content` object.

---

## InceptBench Response (typical)

- `overall`: `{ "score": 0.0–1.0, "reasoning": "...", "suggested_improvements": "..." }`
- Dimension scores: `factual_accuracy`, `curriculum_alignment`, `clarity`, `distractor_quality`, etc.
- Rating: `ACCEPTABLE` | `REVISE` | `REJECT`

---

## Score Conversion

- InceptBench `overall.score` is 0–1. Convert to 0–100: `score_100 = overall.score * 100`.

---

## Quality Targets (Pre-Experiment)

| Metric | Target |
|--------|--------|
| Aggregate Score (average over all items) | ≥ 93 |
| Pass Rate (% of items with overall score > 85) | ≥ 85% |

---

## Acceptance Framework

- **ACCEPT**: Aggregate ≥ 93, Pass rate ≥ 85%, no critical errors.
- **REVISE**: Aggregate 90–92 OR Pass rate 80–84%; fixable issues.
- **REJECT**: Aggregate < 90 OR Pass rate < 80%; structural failure.

---

## Error Handling

- Evaluation failures are non-fatal: questions are still returned.
- Log evaluation errors for analysis.
- If InceptBench is unavailable, omit `evaluation` on the item; do not fail the pipeline.
