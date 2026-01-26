---
name: generate-passage
description: Generate grade-appropriate reading passages for RL.* and RI.* standards. Use for reading comprehension questions.
---

# Generate Passage Skill

Generate grade-appropriate reading passages for Reading Literature (RL.*) and Reading Informational (RI.*) standards.

## When to Use

- Standard contains `RL.` (Reading Literature) → Generate narrative passage
- Standard contains `RI.` (Reading Informational) → Generate informational passage
- **Do NOT use** for Language (L.*) or Writing (W.*) standards

## Usage

Run the script:

```bash
python scripts/generate_passage.py "CCSS.ELA-LITERACY.RL.3.1" "3" "narrative"
```

Arguments:
1. `standard_id`: The standard ID
2. `grade`: Grade level (K, 1-12)
3. `style`: "narrative" or "informational"

## Passage Styles

### Narrative (for RL.* standards)
- Stories, fables, folktales, myths
- Characters, plot, setting
- Beginning, middle, end structure

### Informational (for RI.* standards)
- Articles, explanatory texts
- Facts and information
- Clear organization with main ideas

## Grade-Level Guidelines

| Grade | Age | Word Count | Sentence Style |
|-------|-----|------------|----------------|
| K | 5-6 | 50-100 | Very short (3-6 words) |
| 1-2 | 6-8 | 75-200 | Short, simple sentences |
| 3-5 | 8-11 | 150-350 | Simple/compound mix |
| 6-8 | 11-14 | 300-500 | Complex allowed |
| 9-12 | 14-18 | 450-700 | Sophisticated structures |

## Output

Generate ONLY the passage text. No explanations, no JSON, just the passage.

The passage will be cached for future use.

## Example Output (Grade 3 Narrative)

```
The Little Seed

A tiny seed sat in the dark soil. "I wonder what I will become," it thought.

Day after day, the sun warmed the ground above. Rain soaked through the dirt. The seed began to change.

First, a small root pushed down into the earth. Then, a tiny green stem reached up toward the light. The stem grew taller and taller.

One morning, a beautiful flower opened its petals. The little seed had become a bright yellow sunflower!

"So this is what I was meant to be," the flower said, smiling at the sun.
```

## Critical Rules

- Match vocabulary to grade level
- Keep within word count range
- Include elements that allow comprehension questions
- Make the passage engaging and age-appropriate
