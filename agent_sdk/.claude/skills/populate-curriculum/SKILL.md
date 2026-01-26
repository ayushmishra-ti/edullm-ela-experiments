---
name: populate-curriculum
description: Generate and save Assessment Boundaries and Common Misconceptions for ELA standards. Use when curriculum data is missing for a standard.
---

# Populate Curriculum Skill

Generate Assessment Boundaries and Common Misconceptions for an ELA standard, then save to curriculum.md.

## When to Use

- When `lookup-curriculum` returns missing data (`*None specified*` or empty fields)
- Before generating questions for a new standard
- When you need to create curriculum context

## Usage

Run the script with standard ID and description:

```bash
python scripts/populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A" "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs..."
```

## What You Generate

### Assessment Boundaries
- 1-3 concise bullet points
- Each starts with `* ` (asterisk + space)
- Specifies what IS and is NOT assessed
- Grade-appropriate scope

**Example:**
```
* Assessment is limited to identifying basic parts of speech in simple sentences. Complex sentence structures are out of scope.
* Students should explain functions in general terms. Technical terminology beyond the five basic parts is not assessed.
```

### Common Misconceptions
- 3-5 bullet points
- Each starts with `* ` (asterisk + space)
- One specific misconception per bullet
- Useful for creating MCQ distractors

**Example:**
```
* Students may confuse adjectives with adverbs, thinking any descriptive word is an adjective.
* Students often think that verbs only show physical action, missing linking verbs (is, are, was).
* Students may believe word position determines part of speech, rather than function.
```

## Output Format

Return JSON:
```json
{
  "assessment_boundaries": "* Assessment is limited to...\n* Students should...",
  "common_misconceptions": [
    "Students may confuse...",
    "Students often think...",
    "Students might incorrectly believe..."
  ]
}
```

## After Generation

The script will update `curriculum.md` with the generated content, replacing any `*None specified*` entries.

## Critical Rules

- Use bullet format with `* ` prefix
- Be specific and actionable
- Make misconceptions useful for creating distractors
- Stay grade-appropriate
