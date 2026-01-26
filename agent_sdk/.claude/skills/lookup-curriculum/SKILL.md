---
name: lookup-curriculum
description: Look up assessment boundaries and common misconceptions for ELA standards. Use when you need curriculum context before generating questions.
---

# Lookup Curriculum Skill

Search the curriculum database for assessment boundaries and common misconceptions for a given ELA standard.

## When to Use

- Before generating any ELA question
- When you need to understand what's in/out of scope for a standard
- When you need common misconceptions for creating distractors

## Usage

Run the script with the standard ID:

```bash
python scripts/lookup_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A"
```

## Output

Returns JSON:
```json
{
  "found": true,
  "standard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "standard_description": "Explain the function of nouns...",
  "assessment_boundaries": "* Assessment is limited to...",
  "common_misconceptions": [
    "Students may confuse adjectives with adverbs",
    "Students often think verbs only show physical action"
  ]
}
```

## If Not Found

If the standard is not found or has missing data:
```json
{
  "found": false,
  "standard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "error": "Standard ID not found in curriculum"
}
```

When data is missing, use the `populate-curriculum` skill to generate it.

## How to Use Results

1. **Assessment Boundaries**: Ensure your question stays within these limits
2. **Common Misconceptions**: Use these to create plausible distractors
