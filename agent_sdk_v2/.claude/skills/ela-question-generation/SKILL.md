---
name: ela-question-generation
description: Generate K-12 ELA assessment questions (MCQ, MSQ, Fill-in) as JSON. For RL.*/RI.* standards, read passage guidelines from reference/passage-guidelines.md and generate the passage inline. ALWAYS return valid JSON as final output.
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

| Standard | Requires Passage? | Special Handling |
|----------|-------------------|------------------|
| `RL.*` (Reading Literature) | YES | Generate narrative passage (see below) |
| `RI.*` (Reading Informational) | YES | Generate informational passage (see below) |
| `L.*` (Language) | NO | **Read grammar rules first** (see below); Fill-in OK |
| `W.*` (Writing) | NO | **SCENARIO-BASED only; convert fill-in → MCQ** (see below) |
| `RF.*` (Reading Foundational) | NO | Proceed to Step 2 |
| `SL.*` (Speaking & Listening) | NO | Proceed to Step 2 |

### CRITICAL: For RL.* and RI.* Standards

**Read passage guidelines from:** `reference/passage-guidelines.md`

**Workflow for RL.*/RI.* standards:**
1. Read the passage generation guidelines from `reference/passage-guidelines.md`
2. Generate a passage following those guidelines:
   - `RL.*` → **narrative** style (story, fable, folktale)
   - `RI.*` → **informational** style (article, explanatory text)
3. **DO NOT STOP after generating the passage!**
4. Continue to Step 2 to generate the question JSON
5. Include the passage in the `passage` field of your final JSON output
6. **Your final output MUST be a valid JSON object, not passage text**

**DO NOT invoke any separate skill. Generate the passage yourself following the guidelines.**

### For L.* (Language/Grammar) Standards

**Read grammar rules from:** `reference/grammar-rules.md`

**BEFORE writing any grammar question (L.*):**

1. **Read the grammar reference** to ensure factual accuracy in your explanation
2. Pay special attention to common misconceptions listed in the reference
3. **Verify your explanation** against the grammar rules before finalizing

**Common Factual Errors to Avoid:**

| ❌ WRONG | ✅ CORRECT |
|----------|-----------|
| "Swimming in 'Swimming is fun' is progressive tense" | "Swimming is a gerund functioning as the subject" |
| "Participles only function as adjectives" | "Participial clauses can function adverbially" |
| "Use 'was' in 'If I was rich'" | "Use 'were' in hypotheticals: 'If I were rich'" |

### CRITICAL: For W.* (Writing) Standards

Writing standards are **performance-based** - they assess writing skills, NOT vocabulary recall.

**IMPORTANT RULES for W.* standards:**

1. **Use SCENARIO-BASED questions**: Present a writing scenario and ask students to identify the best approach, revision, or strategy.

2. **Focus on PROCESS, not terminology**: Don't test vocabulary like "stamina" or "fluency". Test actual writing decisions.

3. **Include writing samples**: Provide a short student draft or writing excerpt, then ask about revisions, organization, or improvements.

4. **For Fill-in W.* questions**: Use scenario-based fill-ins with word banks (see example below).

**W.* Question Types (by standard cluster):**

| Standard | Focus | Question Approach |
|----------|-------|-------------------|
| W.*.1 (Opinion/Argument) | Persuasive writing | "Which claim best supports..." / "Which evidence strengthens..." |
| W.*.2 (Informative) | Explanatory writing | "Which transition best connects..." / "How should the writer organize..." |
| W.*.3 (Narrative) | Story writing | "Which detail best develops..." / "How should the writer revise..." |
| W.*.4-6 (Process) | Planning/revising | "What should the writer do next..." / "Which revision improves..." |
| W.*.7-9 (Research) | Research skills | "Which source is most credible..." / "How should the writer cite..." |
| W.*.10 (Routine) | Writing practice | "Which strategy helps build..." / "What is the purpose of..." |

**Example W.* MCQ (Scenario-based):**

```json
{
  "id": "w_6_2_f_mcq_easy_001",
  "content": {
    "question": "A student is writing an informative essay about honeybee communication. Read the draft conclusion:\n\n'Honeybees are interesting insects. They do many things. The end.'\n\nWhich revision would create a stronger conclusion that follows from the information presented?",
    "answer": "C",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "Adding more facts about other insects"},
      {"key": "B", "text": "Restating the introduction word-for-word"},
      {"key": "C", "text": "Summarizing the main points about waggle dances and pheromones"},
      {"key": "D", "text": "Asking the reader a question about their favorite insect"}
    ],
    "answer_explanation": "A strong conclusion for an informative essay should synthesize the main ideas presented in the body. Option C does this by summarizing the key communication methods (waggle dances, pheromones) discussed in the essay. Option A introduces new, unrelated content. Option B is repetitive and doesn't synthesize. Option D shifts to persuasive/personal territory inappropriate for informative writing."
  }
}
```

**Example W.* Fill-in (Scenario-based with word bank):**

```json
{
  "id": "w_6_2_c_fillin_easy_001",
  "content": {
    "question": "A student is writing an informative essay about recycling. Read the two sentences:\n\n'Recycling reduces waste in landfills. ______ it conserves natural resources.'\n\nWhich transition word best connects these related ideas?\n\n(Word choices: However, Additionally, Therefore, Although)",
    "answer": "Additionally",
    "image_url": [],
    "additional_details": "CCSS.ELA-LITERACY.W.6.2.C",
    "acceptable_alternatives": ["Additionally"],
    "answer_explanation": "The two sentences present related benefits of recycling (reduces waste AND conserves resources). 'Additionally' is the correct transition because it shows that the second idea adds to the first. 'However' and 'Although' show contrast, which doesn't fit here. 'Therefore' shows cause-effect, but the second sentence isn't a result of the first."
  }
}
```

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

**Fill-in works for L.* and W.* standards. For W.*, use scenario-based questions with word banks.**

```json
{
  "id": "l_3_1_d_fillin_easy_001",
  "content": {
    "answer": "went",
    "question": "Complete the sentence with the correct past tense form of 'go':\n\nYesterday, Maria ______ to the library to return her books.\n\n(Word choices: go, went, gone, going)",
    "image_url": [],
    "additional_details": "CCSS.ELA-LITERACY.L.3.1.D",
    "acceptable_alternatives": ["went"],
    "answer_explanation": "The word 'Yesterday' tells us the action happened in the past. The verb 'go' has an irregular past tense form. Instead of adding -ed, we change 'go' to 'went' to show past tense."
  }
}
```

**IMPORTANT for Fill-in:**
- **ONLY use for L.* (Language) standards** - NOT for W.*, RL.*, RI.*, RF.*, SL.*
- NO `answer_options` field
- `answer` is the expected text (single word or short phrase)
- Question must have a clear blank (______)
- **ALWAYS include a word bank** in the question: "(Word choices: option1, option2, option3, option4)"
- Include `additional_details` with standard ID
- Include `acceptable_alternatives` array with all valid answers
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

### Standard-Specific Fill-in Guidelines
- **L.* (Language)**: Grammar, verb forms, word choice - standard fill-in with word bank
- **W.* (Writing)**: MUST be scenario-based (transitions, revisions, etc.) - with word bank
- **RL.*/RI.* (Reading)**: Use MCQ with passage instead of fill-in

### Question Design
1. **Use clear context sentences** - Include signal words that help identify the correct form:
   - Time markers: "Yesterday," "Last week," "By next Friday"
   - Comparison indicators: "than the other," "of all the"
   - Subject clues: "The team" (singular) vs "The players" (plural)

2. **Place blanks naturally** - The blank should fit where the word naturally appears
   - Good: "Maria ______ to the library yesterday."
   - Bad: "______ Maria to the library yesterday went."

3. **ALWAYS provide a word bank** (REQUIRED to reduce ambiguity):
   - Format: "(Word choices: option1, option2, option3, option4)"
   - Include the correct answer and 3 plausible distractors
   - Example: "(Word choices: go, went, gone, going)"

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

### Content Quality
- [ ] Only ONE correct answer (MCQ/Fill-in) OR all selected answers correct (MSQ)
- [ ] All distractors are clearly wrong for specific reasons
- [ ] Fill-in: NO `answer_options` field, MUST have word bank
- [ ] **W.* standards: scenario-based, not vocabulary recall**
- [ ] **W.* fill-in: scenario-based with word bank**
- [ ] Question includes context sentence when needed
- [ ] Vocabulary matches grade level
- [ ] If RL/RI standard: question references the passage

### Grammar Accuracy (L.* Standards)
- [ ] **Explanation is factually correct** - verify against `reference/grammar-rules.md`
- [ ] **Stem matches options**: If stem asks about "verbals," options should be about verbals
- [ ] **No ambiguous blanks**: Fill-in blank should have ONE clear correct answer
- [ ] **Correct terminology**: Use proper grammar terms (gerund, participle, infinitive, etc.)

### Format
- [ ] `image_url` is `[]`
- [ ] Answer format: string for MCQ/Fill-in, array for MSQ
- [ ] Exactly 4 options (A, B, C, D) for MCQ/MSQ
- [ ] `answer_options` uses format: `[{"key": "A", "text": "..."}]`

## Critical

- `image_url` is ALWAYS `[]`
- **FINAL OUTPUT MUST BE VALID JSON** - no markdown, no explanations, no passage-only text
- For RL.*/RI.* standards: 
  1. Read passage guidelines from `reference/passage-guidelines.md`
  2. Generate a passage yourself following those guidelines (DO NOT invoke another skill)
  3. **DO NOT STOP after passage generation - continue to create the question!**
  4. Include the passage in the `passage` field of your JSON
  5. Create a question that references the passage
- **Your response must end with a complete JSON object like the examples above**
