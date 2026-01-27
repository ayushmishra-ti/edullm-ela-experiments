---
name: ela-question-generation
description: Generate K-12 ELA assessment questions (MCQ, MSQ, Fill-in) with curriculum context. Use when user asks to generate ELA questions, assessments, or Common Core aligned items. This skill orchestrates curriculum lookup, passage generation, and question generation.
---

# ELA Question Generation

Generate K-12 ELA assessment questions (MCQ, MSQ, Fill-in) aligned to Common Core standards with curriculum context. **You orchestrate the workflow** - decide which tools to use and when.

## When to Use

- User asks to generate ELA questions (MCQ, MSQ, Fill-in)
- User provides a standard ID (e.g., `CCSS.ELA-LITERACY.L.3.1.A`)
- User wants to create assessment items for ELA
- User mentions Common Core standards

## Instructions

### Step 1: Parse the Request
Extract from the request: `grade`, `type` (mcq/msq/fill-in), `difficulty`, `substandard_id`, `substandard_description`

### Step 2: Determine What's Needed

**Check if passage is required:**
- `RL.*` (Reading Literature) → needs narrative passage
- `RI.*` (Reading Informational) → needs informational passage  
- `L.*` or `W.*` (Language/Writing) → no passage needed

**Always get curriculum context** - every question needs it.

### Step 3: Use Available Tools

You have these scripts. **Decide which to run:**

**Curriculum Lookup** (`scripts/lookup_curriculum.py`):
```bash
python scripts/lookup_curriculum.py "<standard_id>"
```
- Returns: Assessment boundaries and common misconceptions
- **Always run this first** for every question

**Populate Curriculum** (`scripts/populate_curriculum.py`):
```bash
python scripts/populate_curriculum.py "<standard_id>" "<standard_description>"
```
- Use when: Curriculum lookup returns missing/empty data
- Generates and saves curriculum info to `curriculum.md`

**Generate Passage** (`scripts/generate_passage.py`):
```bash
python scripts/generate_passage.py "<standard_id>" "<grade>" "<style>"
```
- Use when: Standard is `RL.*` or `RI.*`
- `style`: "narrative" for RL.*, "informational" for RI.*

### Step 4: Generate the Question

Use all gathered context:
- Curriculum boundaries (stay in scope)
- Common misconceptions (design distractors)
- Passage (if RL.*/RI.* standards)
- Grade level (vocabulary, complexity)

**If anything is unclear**, ask the user for clarification before proceeding.

## Input/Output Format

### Input

You receive a request like:
```json
{
  "type": "mcq",
  "grade": "3",
  "skills": {
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
    "substandard_description": "Explain the function of nouns, pronouns, verbs..."
  },
  "difficulty": "easy"
}
```

### Output

The output format depends on the question type in the request:

### MCQ (Multiple Choice) - Single Correct Answer
```json
{
  "id": "l_3_1_a_mcq_easy_001",
  "content": {
    "answer": "B",
    "question": "Which word in this sentence is a noun? The cat sleeps on the soft bed.",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "sleeps"},
      {"key": "B", "text": "cat"},
      {"key": "C", "text": "soft"},
      {"key": "D", "text": "on"}
    ],
    "answer_explanation": "A noun names a person, place, thing, or animal. 'Cat' names an animal, so it is a noun."
  }
}
```

### MSQ (Multiple Select) - Multiple Correct Answers
```json
{
  "id": "l_3_1_a_msq_easy_001",
  "content": {
    "answer": ["A", "D"],
    "question": "Read this sentence: 'The happy dog ran quickly to the park.' Which words are nouns? Select all that apply.",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "dog"},
      {"key": "B", "text": "ran"},
      {"key": "C", "text": "quickly"},
      {"key": "D", "text": "park"}
    ],
    "answer_explanation": "Nouns name people, places, things, or animals. 'Dog' names an animal and 'park' names a place, so both are nouns. 'Ran' is a verb and 'quickly' is an adverb, so they are not correct answers."
  }
}
```

### Fill-in (Fill in the Blank)
```json
{
  "id": "l_3_1_d_fillin_easy_001",
  "content": {
    "answer": "ran",
    "question": "Read this sentence: 'Yesterday, I ___ to the store.' Which verb correctly completes the sentence?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "run"},
      {"key": "B", "text": "runs"},
      {"key": "C", "text": "ran"},
      {"key": "D", "text": "running"}
    ],
    "answer_explanation": "The sentence says 'Yesterday,' which means the action happened in the past. 'Ran' is the past tense form of 'run.'"
  }
}
```

---

## Best Practices

### Question Design Principles

1. **Unambiguous answers**: Only ONE correct answer for MCQ/Fill-in. For MSQ, ALL selected answers must be correct.
2. **Context sentences**: Include example sentences when testing parts of speech, word function, or grammar.
3. **Clear constraints**: If a question could have multiple correct answers, add constraints (e.g., "Yesterday" = past tense).
4. **Distractor design**: Use common misconceptions from curriculum lookup, not random wrong answers.
5. **Grade-appropriate**: Match vocabulary and sentence complexity to the grade level.

### Domain-Specific Conventions

- **Parts of speech questions**: Always provide a context sentence
- **Verb tense questions**: Include time markers (yesterday, today, tomorrow)
- **Fill-in questions**: The blank should have only one grammatically correct option
- **MSQ questions**: Must say "Select all that apply" or "Select all correct answers"

---

## Examples

### Example 1: MCQ - Parts of Speech (Easy)

**Input:**
```json
{
  "type": "mcq",
  "grade": "3",
  "skills": {
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
    "substandard_description": "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences."
  },
  "difficulty": "easy"
}
```

**Curriculum Context (from lookup):**
- Assessment Boundaries: Limited to five basic parts of speech in simple sentences
- Common Misconceptions: Students may confuse adjectives with adverbs; students often think verbs only show physical action

**Output:**
```json
{
  "id": "l_3_1_a_mcq_easy_001",
  "content": {
    "answer": "D",
    "question": "Read this sentence: 'The happy dog ran quickly to the park.' What is the function of the word 'quickly' in this sentence?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "It names the dog"},
      {"key": "B", "text": "It shows what the dog did"},
      {"key": "C", "text": "It describes the dog"},
      {"key": "D", "text": "It tells how the dog ran"}
    ],
    "answer_explanation": "The word 'quickly' is an adverb. It tells how the dog ran. Adverbs describe verbs and tell how, when, or where something happens. 'Quickly' tells how the action (ran) was done."
  }
}
```

**Why this is good:**
- ✅ Includes context sentence ("Read this sentence: ...")
- ✅ Only ONE correct answer (D) - all others are clearly wrong
- ✅ Distractors reflect common misconceptions (A: noun confusion, B: verb confusion, C: adjective confusion)
- ✅ Grade-appropriate vocabulary
- ✅ Clear explanation

---

### Example 2: Fill-in Question (Medium)

**Input:**
```json
{
  "type": "fill-in",
  "grade": "3",
  "skills": {
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.D",
    "substandard_description": "Form and use regular and irregular verbs."
  },
  "difficulty": "medium"
}
```

**Output:**
```json
{
  "id": "l_3_1_d_fillin_medium_001",
  "content": {
    "answer": "ran",
    "question": "Read this sentence: 'Yesterday, I ___ to the store to buy milk.' Which verb correctly completes the sentence?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "run"},
      {"key": "B", "text": "runs"},
      {"key": "C", "text": "ran"},
      {"key": "D", "text": "running"}
    ],
    "answer_explanation": "The sentence says 'Yesterday,' which means the action happened in the past. 'Ran' is the past tense form of 'run.' 'Run' is present tense, 'runs' is present tense for he/she/it, and 'running' needs a helping verb like 'was' or 'is.'"
  }
}
```

**Why this is good:**
- ✅ Context sentence provided
- ✅ Constraint clearly stated ("Yesterday" = past tense)
- ✅ Only ONE correct answer (C) - others are wrong for specific reasons
- ✅ Distractors test common errors (wrong tense forms)
- ✅ Explanation addresses why each option is wrong

---

### Example 3: MSQ - Multiple Select (Medium)

**Input:**
```json
{
  "type": "msq",
  "grade": "3",
  "skills": {
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
    "substandard_description": "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences."
  },
  "difficulty": "medium"
}
```

**Output:**
```json
{
  "id": "l_3_1_a_msq_medium_001",
  "content": {
    "answer": ["A", "B"],
    "question": "Read this sentence: 'The happy dog ran quickly to the green park.' Which words are adjectives that describe nouns? Select all that apply.",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "happy"},
      {"key": "B", "text": "green"},
      {"key": "C", "text": "quickly"},
      {"key": "D", "text": "ran"}
    ],
    "answer_explanation": "Adjectives describe nouns. 'Happy' describes the noun 'dog' and 'green' describes the noun 'park.' Both are adjectives. 'Quickly' is an adverb (describes the verb 'ran'), and 'ran' is a verb, so they are not correct answers."
  }
}
```

**Why this is good:**
- ✅ Context sentence provided
- ✅ Multiple correct answers clearly specified (A and B)
- ✅ Question explicitly asks for adjectives (not adverbs)
- ✅ Distractors include common confusions (adverb, verb)
- ✅ All selected answers must be correct
- ✅ Answer is an array: `["A", "B"]` not a single string

---

### Example 4: MCQ - Verb Tenses (Hard)

**Input:**
```json
{
  "type": "mcq",
  "grade": "3",
  "skills": {
    "substandard_id": "CCSS.ELA-LITERACY.L.3.1.E",
    "substandard_description": "Form and use the simple (e.g., I walked; I walk; I will walk) verb tenses."
  },
  "difficulty": "hard"
}
```

**Output:**
```json
{
  "id": "l_3_1_e_mcq_hard_001",
  "content": {
    "answer": "B",
    "question": "Read these sentences: 'Last week, Maria walked to school every day. Today, she walks to school. Tomorrow, she will walk to school.' Which sentence shows the simple future tense?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "Last week, Maria walked to school every day."},
      {"key": "B", "text": "Tomorrow, she will walk to school."},
      {"key": "C", "text": "Today, she walks to school."},
      {"key": "D", "text": "All three sentences show future tense"}
    ],
    "answer_explanation": "The simple future tense uses 'will' + the base form of the verb. 'Tomorrow, she will walk' uses 'will walk,' which is the simple future tense. 'Walked' is past tense, 'walks' is present tense, and option D is incorrect because only one sentence uses future tense."
  }
}
```

**Why this is good:**
- ✅ Multiple sentences provided for comparison
- ✅ Clear time markers (Last week, Today, Tomorrow)
- ✅ Only ONE correct answer (B)
- ✅ Tests understanding of all three tenses
- ✅ Distractor D tests if student understands only one is correct

---

## Grade Level Guidelines

| Grade | Age | Vocabulary |
|-------|-----|------------|
| K | 5-6 | Simple sight words |
| 1-2 | 6-8 | Common everyday words |
| 3-5 | 8-11 | Grade-level vocabulary |
| 6-8 | 11-14 | Academic vocabulary |
| 9-12 | 14-18 | Sophisticated, literary terms |

## Difficulty Definitions

- **Easy**: Recall, one concept, familiar words
- **Medium**: Apply a rule, compare options
- **Hard**: Multiple concepts, subtle wording

## ID Generation

From `CCSS.ELA-LITERACY.L.3.1.A`:
1. Take part after `CCSS.ELA-LITERACY.` → `L.3.1.A`
2. Lowercase and replace `.` with `_` → `l_3_1_a`
3. Append `_<type>_<difficulty>_001` where `<type>` is:
   - `mcq` for multiple choice
   - `msq` for multiple select
   - `fillin` or `fill-in` for fill-in-the-blank

Examples:
- `l_3_1_a_mcq_easy_001`
- `l_3_1_a_msq_medium_001`
- `l_3_1_d_fillin_easy_001`

## Quality Checklist

Before returning a question, verify:

- [ ] Only ONE correct answer (MCQ/Fill-in) OR all selected answers are correct (MSQ)
- [ ] All distractors are clearly wrong for specific reasons
- [ ] Question includes context sentence when needed
- [ ] Distractors reflect common misconceptions from curriculum lookup
- [ ] Question stays within assessment boundaries
- [ ] Vocabulary matches grade level
- [ ] `image_url` is `[]`
- [ ] Answer format matches type: string for MCQ/Fill-in, array for MSQ

---

## Critical

- `image_url` is ALWAYS `[]`
- Run curriculum lookup for EVERY question
- If passage needed, include it in your question context
- Return ONLY the JSON object, no markdown, no explanations
- Think critically: Could a student argue any other option is correct? If yes, revise.
