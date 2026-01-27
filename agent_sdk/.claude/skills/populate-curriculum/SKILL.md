---
name: populate-curriculum
description: Generate and save Assessment Boundaries and Common Misconceptions for ELA standards. Use when curriculum data is missing for a standard.
---

# Populate Curriculum

Generate Assessment Boundaries and Common Misconceptions for an ELA standard, then save to curriculum.md.

## When to Use

- When `lookup-curriculum` returns missing data (`*None specified*` or empty fields)
- Before generating questions for a new standard that doesn't have curriculum data
- When you need to create curriculum context for question generation

## Instructions

### Step 1: Run the Populate Script

Execute with standard ID and description:

```bash
python scripts/populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A" "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs..."
```

### Step 2: Generate Assessment Boundaries

Create 1-3 concise bullet points that specify:
- What IS assessed (scope)
- What is NOT assessed (out of scope)
- Grade-appropriate limitations

**Format:** Each bullet starts with `* ` (asterisk + space)

**Example:**
```
* Assessment is limited to identifying basic parts of speech in simple sentences. Complex sentence structures are out of scope.
* Students should explain functions in general terms. Technical terminology beyond the five basic parts is not assessed.
```

### Step 3: Generate Common Misconceptions

Create 3-5 bullet points of typical student errors:
- One specific misconception per bullet
- Must be useful for creating MCQ distractors
- Based on real student thinking patterns

**Format:** Each bullet starts with `* ` (asterisk + space)

**Example:**
```
* Students may confuse adjectives with adverbs, thinking any descriptive word is an adjective.
* Students often think that verbs only show physical action, missing linking verbs (is, are, was).
* Students may believe word position determines part of speech, rather than function.
```

### Step 4: Return JSON Format

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

The script will automatically update `curriculum.md` with the generated content.

## Best Practices

- **Be specific**: Vague boundaries lead to out-of-scope questions
- **Actionable misconceptions**: Each misconception should help create a specific distractor
- **Grade-appropriate**: Consider what students at this grade level actually misunderstand
- **Concise**: Keep bullets to 1-2 sentences each
- **Consistent format**: Always use `* ` prefix for bullets
