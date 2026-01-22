---
name: ela-mcq-generation
description: Generate Grade 3 ELA multiple-choice questions aligned to Common Core with curriculum context. Output is JSON only; no images. Uses curriculum lookup for assessment boundaries and misconceptions.
---

# Grade 3 ELA MCQ Generation Skill (Agent SDK)

This skill generates Grade 3 ELA multiple-choice questions aligned to Common Core standards. Questions are output as JSON only - no images are generated.

## Purpose

- Generate MCQ questions aligned to `substandard_id` and `substandard_description`
- Match grade level and difficulty (easy / medium / hard)
- Produce exactly 4 options (A–D), one correct, with `answer_explanation`
- `image_url` is always `[]` (no image generation)
- **Use curriculum context** from `curriculum.md` to ensure alignment with assessment boundaries and create distractors based on common misconceptions

---

## Curriculum Lookup

Before generating any question, you must look up the curriculum information for the given `substandard_id`. This context is essential for creating questions that stay within scope and use real student misconceptions.

### Available Tools

1. **Curriculum Lookup Script**: `curriculum_lookup.py`
   - Location: `option_c_agent_sdk/curriculum_lookup.py`
   - Function: `lookup_curriculum(substandard_id, curriculum_path)`
   - This script searches `curriculum.md` and returns:
     - Assessment Boundaries
     - Common Misconceptions
     - Standard Description

2. **Curriculum File**: `curriculum.md`
   - Location: `option_c_agent_sdk/curriculum.md`
   - Contains Grade 3 ELA standards with assessment boundaries and misconceptions

### How to Use Curriculum Lookup

**Option 1: Use the Python script directly**
```python
# Read and execute the curriculum lookup script
from pathlib import Path
import sys
sys.path.insert(0, 'option_c_agent_sdk')
from curriculum_lookup import lookup_curriculum

result = lookup_curriculum('CCSS.ELA-LITERACY.L.3.1.A', Path('option_c_agent_sdk/curriculum.md'))
```

**Option 2: Use Bash to run the script**
```bash
# If the script is executable, you can run it via Bash tool
python option_c_agent_sdk/curriculum_lookup.py <substandard_id>
```

**Option 3: Read curriculum.md directly and parse**
- Use the Read tool to read `option_c_agent_sdk/curriculum.md`
- Search for the matching `Standard ID: <substandard_id>`
- Extract the `Assessment Boundaries:` and `Common Misconceptions:` sections

### When to Use Curriculum Lookup

You should always look up curriculum information when generating a question. This ensures that:
- The question stays within the assessment boundaries for the standard
- Distractors reflect actual student misconceptions rather than arbitrary errors
- The question is appropriate for Grade 3 level expectations

The curriculum lookup script is available and should be used for every question generation.

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
2. **Distractors**: Reflect common mistakes (e.g. wrong verb form, wrong part of speech, wrong convention). **Use the common misconceptions from curriculum lookup to inform distractor design.** Same format and similar length.
3. **No ambiguity**: Only one option may be correct. Re-check before returning.
4. **Grade 3**: Vocabulary and sentence length suitable for 8–9 year olds.
5. **Alignment**: Question and explanation must match `substandard_description`.
6. **Assessment Boundaries**: Ensure your question stays within the assessment boundaries found in the curriculum lookup. Do not test concepts outside the specified scope.

---

## Workflow

1. **Receive request** with `substandard_id`
2. **Look up curriculum** using `curriculum_lookup.py` or by reading `curriculum.md`
3. **Extract**:
   - Assessment Boundaries (what's in/out of scope)
   - Common Misconceptions (for distractor design)
4. **Generate question** that:
   - Stays within assessment boundaries
   - Uses common misconceptions to create effective distractors
   - Matches the difficulty level
5. **Return JSON** following the output schema

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

**Before generating, look up curriculum:**
- Use `curriculum_lookup.py` with `substandard_id: "CCSS.ELA-LITERACY.L.3.1.E"`
- Extract assessment boundaries and common misconceptions
- Use this context to inform question generation

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

## Critical Requirements

- Always look up curriculum information before generating a question - this is not optional
- The curriculum lookup script is located at `option_c_agent_sdk/curriculum_lookup.py`
- Return only the JSON object - no markdown code fences, no explanatory text outside the JSON
- `image_url` must always be an empty array `[]`
- `answer_options` must be an array with exactly 4 items, each with `{"key":"A"|"B"|"C"|"D","text":"..."}`
- `answer` must match one of the keys in `answer_options`
- Use the assessment boundaries to ensure your question stays within scope
- Use the common misconceptions to create distractors that reflect real student errors
