---
name: generate-passage
description: Generate grade-appropriate reading passages for RL.* and RI.* standards. Use for reading comprehension questions.
---

# Generate Passage

Generate grade-appropriate reading passages for Reading Literature (RL.*) and Reading Informational (RI.*) standards.

## When to Use

- Standard contains `RL.` (Reading Literature) → Generate narrative passage
- Standard contains `RI.` (Reading Informational) → Generate informational passage
- **Do NOT use** for Language (L.*) or Writing (W.*) standards - these don't need passages

## Instructions

### Step 1: Determine Passage Style

- `RL.*` standards → **narrative** (stories, fables, folktales, myths)
- `RI.*` standards → **informational** (articles, explanatory texts)

### Step 2: Run the Generate Script

```bash
python scripts/generate_passage.py "CCSS.ELA-LITERACY.RL.3.1" "3" "narrative"
```

Arguments:
1. `standard_id`: The standard ID (e.g., "CCSS.ELA-LITERACY.RL.3.1")
2. `grade`: Grade level (K, 1-12)
3. `style`: "narrative" or "informational"

### Step 3: Generate the Passage

The script will check cache first. If not cached, generate a passage that:
- Matches the grade-level word count and readability
- Uses appropriate sentence structure
- Includes elements that allow comprehension questions
- Is engaging and age-appropriate

### Step 4: Return Passage Text

Generate **ONLY the passage text**. No explanations, no JSON, no metadata - just the passage.

The passage will be automatically cached for future use.

## Best Practices

### Passage Styles

**Narrative (RL.*):**
- Stories, fables, folktales, myths
- Characters, plot, setting
- Beginning, middle, end structure
- Engaging story elements

**Informational (RI.*):**
- Articles, explanatory texts
- Facts and information
- Clear organization with main ideas
- Topic-appropriate content

### Grade-Level Guidelines

| Grade | Age | Word Count | Sentence Style |
|-------|-----|------------|----------------|
| K | 5-6 | 50-100 | Very short (3-6 words) |
| 1-2 | 6-8 | 75-200 | Short, simple sentences |
| 3-5 | 8-11 | 150-350 | Simple/compound mix |
| 6-8 | 11-14 | 300-500 | Complex allowed |
| 9-12 | 14-18 | 450-700 | Sophisticated structures |

### Domain-Specific Conventions

- Match vocabulary to grade level exactly
- Keep within word count range for the grade
- Include elements that allow comprehension questions aligned to the standard
- Make the passage engaging and age-appropriate
- Use proper paragraph structure

## Example Output (Grade 3 Narrative)

```
The Little Seed

A tiny seed sat in the dark soil. "I wonder what I will become," it thought.

Day after day, the sun warmed the ground above. Rain soaked through the dirt. The seed began to change.

First, a small root pushed down into the earth. Then, a tiny green stem reached up toward the light. The stem grew taller and taller.

One morning, a beautiful flower opened its petals. The little seed had become a bright yellow sunflower!

"So this is what I was meant to be," the flower said, smiling at the sun.
```
