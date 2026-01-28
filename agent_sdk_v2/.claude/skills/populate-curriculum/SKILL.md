---
name: populate-curriculum
description: Generate curriculum data (learning objectives, assessment boundaries, common misconceptions) for ELA standards. Run this BEFORE question generation to pre-fill curriculum.md.
---

# Populate Curriculum

Generate curriculum data for ELA standards. This is a **pre-generation step** - run it to populate curriculum.md before generating questions.

## When to Use

- Before batch question generation
- When curriculum.md is missing data for a standard
- To pre-fill assessment boundaries and misconceptions for new standards

## What to Generate

For each standard, generate:

### 1. Learning Objectives (2-4 bullet points)

What a student should be able to do to demonstrate mastery:
- Use student-facing, measurable verbs (identify, explain, choose, revise, etc.)
- Must reflect the standard description exactly
- No drift to adjacent standards

### 2. Assessment Boundaries (1-3 bullet points)

What IS and is NOT assessed:
- Keep each bullet to 1-2 sentences max
- Focus on grade-appropriate scope
- Clarify limits (e.g., "Limited to simple sentences")

### 3. Common Misconceptions (3-5 bullet points)

Typical student errors:
- One specific misconception per bullet
- These will be used to create effective MCQ distractors
- Focus on errors students actually make

## Input Format

You receive a standard request:

```json
{
  "standard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "standard_description": "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences.",
  "grade": "3"
}
```

## Output Format

Return a JSON object:

```json
{
  "standard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "learning_objectives": [
    "Students can identify nouns, pronouns, verbs, adjectives, and adverbs in sentences",
    "Students can explain what each part of speech does in a sentence",
    "Students can choose the correct part of speech to complete a sentence"
  ],
  "assessment_boundaries": [
    "Assessment is limited to five basic parts of speech: nouns, pronouns, verbs, adjectives, adverbs",
    "Students should identify parts of speech in simple and compound sentences only",
    "Does not include advanced concepts like gerunds, participles, or conjunctive adverbs"
  ],
  "common_misconceptions": [
    "Students may confuse adjectives with adverbs (e.g., thinking 'quick' describes how someone runs)",
    "Students often think verbs only show physical action (missing mental verbs like 'think', 'believe')",
    "Students may confuse pronouns with nouns (e.g., not recognizing 'he' as a pronoun)",
    "Students might think all words ending in '-ly' are adverbs (e.g., 'friendly' is an adjective)",
    "Students may not recognize linking verbs as verbs (e.g., 'is', 'seems', 'becomes')"
  ]
}
```

## Quality Guidelines

### Learning Objectives
- Start with "Students can..." or similar
- Use action verbs: identify, explain, choose, revise, apply, distinguish
- Be specific to the standard, not generic

### Assessment Boundaries
- State what IS assessed first
- Then clarify what is NOT assessed
- Keep grade-appropriate (don't exceed grade level complexity)

### Common Misconceptions
- Be specific (not "students get confused")
- Include examples where helpful
- Focus on errors that make good MCQ distractors

## Examples by Standard Type

### Language (L.*) Standards

Focus on:
- Grammar rules students misapply
- Word form confusions
- Punctuation errors

### Reading Literature (RL.*) Standards

Focus on:
- Misunderstanding story elements
- Confusing character motivations
- Missing theme vs plot

### Reading Informational (RI.*) Standards

Focus on:
- Confusing main idea with details
- Missing text structure
- Misidentifying author's purpose

## Critical

- Return ONLY the JSON object
- No markdown code fences
- All arrays must have proper content (no empty strings)
- Misconceptions should be usable as MCQ distractors
