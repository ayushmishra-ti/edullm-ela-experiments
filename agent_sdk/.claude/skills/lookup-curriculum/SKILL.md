---
name: lookup-curriculum
description: Look up assessment boundaries and common misconceptions for ELA standards. Use when you need curriculum context before generating questions.
---

# Lookup Curriculum

Search the curriculum database for assessment boundaries and common misconceptions for a given ELA standard.

## When to Use

- Before generating any ELA question (required step)
- When you need to understand what's in/out of scope for a standard
- When you need common misconceptions for creating effective distractors

## Instructions

### Step 1: Run the Lookup Script

Execute the curriculum lookup script with the standard ID:

```bash
python scripts/lookup_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A"
```

### Step 2: Check the Results

**If found:**
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

**If not found or missing data:**
```json
{
  "found": false,
  "standard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "error": "Standard ID not found in curriculum"
}
```

### Step 3: Handle Missing Data

If `found: false` or fields are empty/`*None specified*`:
- Use the `populate-curriculum` skill to generate the missing data
- Then re-run lookup to get the populated data

### Step 4: Use the Results

- **Assessment Boundaries**: Ensure your question stays within these limits
- **Common Misconceptions**: Use these to create plausible distractors that reflect real student errors

## Best Practices

- Always run curriculum lookup before generating questions
- If data is missing, populate it first rather than proceeding without context
- Use assessment boundaries to ensure questions stay in scope
- Use misconceptions to design distractors that test real student understanding
