---
name: ela-question-generation
description: Generate K-12 ELA assessment questions (MCQ, MSQ, Fill-in) aligned to Common Core standards. Use when asked to create ELA questions, assessment items, or Common Core aligned questions.
---

# ELA Question Generation

Generate K-12 ELA assessment questions (MCQ, MSQ, Fill-in) aligned to Common Core standards.

## When to Use

- Generate ELA questions (MCQ, MSQ, Fill-in)
- Standard ID provided (e.g., `CCSS.ELA-LITERACY.L.3.1.A`)
- Create assessment items for ELA / Common Core

## Workflow

### Step 1: Check if Passage is Required

**Route by standard family:**

| Standard | Requires Passage? | Passage Style |
|----------|-------------------|---------------|
| `RL.*` (Reading Literature) | YES | narrative |
| `RI.*` (Reading Informational) | YES | informational |
| `L.*` (Language) | NO | - |
| `W.*` (Writing) | NO | - |
| `RF.*` (Reading Foundational) | NO | - |
| `SL.*` (Speaking & Listening) | NO | - |

**If passage is required (RL.*/RI.*)**, generate the passage INLINE (do NOT call a separate skill):

1. Create a grade-appropriate passage (150-400 words depending on grade)
2. For `RL.*`: narrative style (story, fable, folktale)
3. For `RI.*`: informational style (article, explanatory text)
4. Include the passage in the `passage` field of the JSON output
5. Then create a comprehension question anchored to the passage

**Passage Guidelines by Grade:**
| Grade | Word Count | Style |
|-------|------------|-------|
| 2-3 | 100-200 | Simple sentences, familiar topics |
| 4-5 | 150-250 | Compound sentences, varied vocabulary |
| 6-8 | 200-350 | Complex sentences, academic vocabulary |
| 9-12 | 300-450 | Sophisticated structure, literary devices |

### Step 2: Generate the Question

Use the request context:
- `substandard_description` (governing topic/scope)
- Grade level (vocabulary, complexity)
- Difficulty (easy, medium, hard)
- Passage text (if RL.*/RI.* standard)

**Topic fidelity (non-negotiable):**
- The question MUST directly assess the `substandard_description`
- Every part (prompt, answer, distractors, explanation) must reflect the standard
- If the standard is broad, pick ONE clear micro-skill and stay narrowly focused

## Output Formats

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

### MCQ with Passage (for RL.*/RI.* standards)

```json
{
  "id": "rl_6_4_mcq_easy_001",
  "content": {
    "passage": "The Storm\n\nMaya stood at the window, watching dark clouds accumulate on the horizon. The meteorologist had predicted severe weather, and now the signs were unmistakable. Trees swayed violently as gusts of wind battered the neighborhood.\n\n\"We should secure the outdoor furniture,\" her father suggested, his voice calm but urgent. Maya nodded and followed him outside. They worked quickly, moving chairs and cushions into the garage before the first drops of rain began to fall.",
    "answer": "C",
    "question": "Based on the passage, what does the word 'accumulate' most likely mean?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "disappear quickly"},
      {"key": "B", "text": "change color"},
      {"key": "C", "text": "gather together"},
      {"key": "D", "text": "move apart"}
    ],
    "answer_explanation": "In the passage, Maya watches dark clouds 'accumulate on the horizon.' The context shows clouds building up before a storm, indicating that 'accumulate' means to gather together or collect in increasing amounts."
  }
}
```

### MSQ (Multiple Select) - Multiple Correct Answers

```json
{
  "id": "l_3_1_a_msq_medium_001",
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
    "answer_explanation": "Nouns name people, places, things, or animals. 'Dog' names an animal and 'park' names a place."
  }
}
```

### Fill-in (Fill in the Blank) - NO answer_options

```json
{
  "id": "l_3_1_d_fillin_easy_001",
  "content": {
    "answer": "went",
    "question": "Complete the sentence with the correct past tense form of 'go':\n\nYesterday, Maria ______ to the library to return her books.",
    "image_url": [],
    "additional_details": "CCSS.ELA-LITERACY.L.3.1.D",
    "answer_explanation": "The word 'Yesterday' tells us the action happened in the past. The verb 'go' has an irregular past tense form. Instead of adding -ed, we change 'go' to 'went' to show past tense."
  }
}
```

**IMPORTANT for Fill-in:**
- NO `answer_options` field
- `answer` is the expected text (single word or short phrase)
- Question must have a clear blank (______)
- Include `additional_details` with standard ID
- Explanation MUST NOT reference option letters (A/B/C/D)
- Explanation should teach the underlying rule, not just state the answer

**For high-quality Fill-in questions, see:** `reference/fill-in-examples.md`

This file contains grade-specific examples (Grades 3, 5, 6, 8) demonstrating:
- Proper context and signal words (e.g., "Yesterday" for past tense)
- Clear blank placement within natural sentence flow
- Educational explanations that teach the grammar rule
- Appropriate difficulty scaling by grade level

## ID Generation

From `CCSS.ELA-LITERACY.L.3.1.A`:
1. Take part after `CCSS.ELA-LITERACY.` → `L.3.1.A`
2. Lowercase and replace `.` with `_` → `l_3_1_a`
3. Append `_<type>_<difficulty>_001`

Examples:
- `l_3_1_a_mcq_easy_001`
- `ri_5_2_msq_medium_001`
- `rl_6_1_fillin_hard_001`

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

## Fill-in Question Best Practices

Fill-in questions have the lowest pass rates. Follow these guidelines strictly:

### Question Design
1. **Use clear context sentences** - Include signal words that help identify the correct form:
   - Time markers: "Yesterday," "Last week," "By next Friday"
   - Comparison indicators: "than the other," "of all the"
   - Subject clues: "The team" (singular) vs "The players" (plural)

2. **Place blanks naturally** - The blank should fit where the word naturally appears
   - Good: "Maria ______ to the library yesterday."
   - Bad: "______ Maria to the library yesterday went."

3. **Provide word bank or base form when helpful**:
   - "(go / went / going)" for clarity
   - "Write the correct form of 'swim'" when testing conjugation

### Answer Specifications
- Answer must be **exactly one word or short phrase**
- Avoid answers with multiple acceptable spellings unless all are listed
- Test ONE specific skill per question (don't combine verb tense + spelling)

### Explanation Requirements
- **Teach the rule**, don't just state the answer
- Explain WHY incorrect alternatives would be wrong
- Connect to the grammar concept being tested
- NEVER mention option letters (A, B, C, D) - fill-ins have no options

### Grade-Specific Focus
| Grade | Focus Areas |
|-------|-------------|
| 3 | Irregular verbs, comparative/superlative adjectives, subject-verb agreement |
| 5 | Perfect tenses (present/past/future), verb tense consistency |
| 6 | Pronouns (intensive, reflexive, case), pronoun-antecedent agreement |
| 8 | Verbals (gerunds, infinitives, participles), active/passive voice, subjunctive mood |

## Quality Checklist

Before returning a question, verify:

- [ ] Only ONE correct answer (MCQ/Fill-in) OR all selected answers correct (MSQ)
- [ ] All distractors are clearly wrong for specific reasons
- [ ] Fill-in: NO `answer_options` field
- [ ] Question includes context sentence when needed
- [ ] Vocabulary matches grade level
- [ ] `image_url` is `[]`
- [ ] Answer format: string for MCQ/Fill-in, array for MSQ
- [ ] If RL/RI standard: question references the passage

## Critical

- `image_url` is ALWAYS `[]`
- Return ONLY the JSON object, no markdown, no explanations
- For RL.*/RI.* standards: include `passage` field in the content, question must reference the passage
- Generate passage INLINE (do NOT call separate skill) - include everything in one JSON response
