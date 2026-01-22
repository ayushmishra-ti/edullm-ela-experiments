---
name: ela-mcq-generation
description: Generate Grade 3 ELA multiple-choice questions aligned to Common Core. Output is JSON only; no images. Covers easy/medium/hard difficulty and distractor rules.
---

# Grade 3 ELA MCQ Generation Skill

This Claude Code Skill generates Grade 3 ELA multiple-choice questions from Common Core standards. **No images.** Output is JSON only.

## Purpose

- Generate MCQ questions aligned to `substandard_id` and `substandard_description`
- Match grade level and difficulty (easy / medium / hard)
- Produce exactly 4 options (A–D), one correct, with `answer_explanation`
- `image_url` is always `[]` (no image generation)

---

## Input Schema

You receive a single request object:

```json
{
  "type": "mcq",
  "grade": "3",
  "skills": {
    "lesson_title": "",
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.D",
    "substandard_description": "Form and use regular and irregular verbs."
  },
  "subject": "ela",
  "curriculum": "common core",
  "difficulty": "easy"
}
```

---

## Output Schema

Respond with **only** valid JSON in this shape (no markdown, no extra text):

```json
{
  "id": "l_3_1_d_mcq_easy_001",
  "content": {
    "answer": "B",
    "question": "Which sentence uses the correct past tense form of the verb 'run'?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "She run to the store yesterday."},
      {"key": "B", "text": "She ran to the store yesterday."},
      {"key": "C", "text": "She runs to the store yesterday."},
      {"key": "D", "text": "She running to the store yesterday."}
    ],
    "additional_details": "",
    "answer_explanation": "The past tense of 'run' is 'ran'. 'Run' is irregular, so it does not take -ed. 'Runs' is present; 'running' needs a helping verb like 'was'."
  }
}
```

### Field rules

| Field | Type | Rules |
|-------|------|--------|
| `id` | string | From `substandard_id`: e.g. `CCSS.ELA-LITERACY.L.3.1.E` → `l_3_1_e`. Then `_mcq_` + `difficulty` + `_001`. Example: `l_3_1_e_mcq_easy_001`. |
| `content.answer` | `"A"` \| `"B"` \| `"C"` \| `"D"` | Key of the correct option. |
| `content.question` | string | Clear, grade-3 appropriate stem. |
| `content.image_url` | array | **Always `[]`.** Do not add image descriptions. |
| `content.answer_options` | array | Exactly 4 items: `{"key": "A"|"B"|"C"|"D", "text": "..."}`. |
| `content.additional_details` | string | Optional metadata; may be `""`. |
| `content.answer_explanation` | string | Why the correct answer is right and why others are wrong; cite the standard where useful. |

---

## Difficulty (from best-practice prompts)

- **Easy**: Literal understanding, recall, one clear concept. Short stems, familiar words.
- **Medium**: Apply a rule in a new sentence, choose the best fit, compare two options.
- **Hard**: Several concepts at once, non-obvious errors, or subtle wording.

---

## Distractor and quality rules

1. **Four options**: A, B, C, D. One correct, three plausible distractors.
2. **Distractors**: Reflect common mistakes (e.g. wrong verb form, wrong part of speech, wrong convention). Same format and similar length.
3. **No ambiguity**: Only one option may be correct. Re-check before returning.
4. **Grade 3**: Vocabulary and sentence length suitable for 8–9 year olds.
5. **Alignment**: Question and explanation must match `substandard_description`.

---

## ID generation

From `substandard_id`:

- `CCSS.ELA-LITERACY.L.3.1.E` → `l_3_1_e`
- `CCSS.ELA-LITERACY.RL.3.2` → `rl_3_2`
- `CCSS.ELA-LITERACY.RI.3.4` → `ri_3_4`

Pattern: take the part after `CCSS.ELA-LITERACY.`, lowercase, replace `.` with `_`. Then append `_mcq_`, then `difficulty`, then `_001`.

---

## Example

**Input:**

```json
{
  "type": "mcq",
  "grade": "3",
  "skills": {
    "lesson_title": "",
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.E",
    "substandard_description": "Form and use the simple (e.g., I walked; I walk; I will walk) verb tenses."
  },
  "subject": "ela",
  "curriculum": "common core",
  "difficulty": "easy"
}
```

**Output:**

```json
{
  "id": "l_3_1_e_mcq_easy_001",
  "content": {
    "answer": "B",
    "question": "Which sentence shows the simple past tense of the verb 'walk'?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "I walk to the park every day."},
      {"key": "B", "text": "I walked to the park yesterday."},
      {"key": "C", "text": "I will walk to the park tomorrow."},
      {"key": "D", "text": "I am walking to the park now."}
    ],
    "additional_details": "",
    "answer_explanation": "The sentence 'I walked to the park yesterday' uses the simple past tense form of 'walk', which is 'walked'. 'Walked' shows an action that already happened."
  }
}
```

---

## Critical

- Respond with **only** the JSON object. No `\`\`\`json`, no preamble, no explanation outside the JSON.
- `image_url` must always be `[]`.
- `answer_options` must be an array of `{"key":"A"|"B"|"C"|"D","text":"..."}`.
- `answer` must match one of the keys in `answer_options`.
