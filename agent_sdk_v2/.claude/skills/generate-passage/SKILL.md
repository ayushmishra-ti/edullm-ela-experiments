---
name: generate-passage
description: Generate grade-appropriate reading passages for Reading Literature (RL.*) and Reading Informational (RI.*) standards. Use when a passage is needed for comprehension questions or reading assessments.
---

# Generate Passage

Generate grade-appropriate reading passages for Reading Literature (RL.*) and Reading Informational (RI.*) standards.

## When to Use

- Standard contains `RL.` (Reading Literature) → Generate **narrative** passage
- Standard contains `RI.` (Reading Informational) → Generate **informational** passage
- **Do NOT use** for Language (L.*), Writing (W.*), or other standards

## Passage Styles

### Narrative (for RL.* standards)

- Stories, fables, folktales, myths
- Characters, plot, setting
- Beginning, middle, end structure
- Engaging story elements
- Age-appropriate themes

### Informational (for RI.* standards)

- Articles, explanatory texts
- Facts and information
- Clear organization with main ideas
- Topic-appropriate content
- Educational value

## Grade-Level Guidelines

| Grade | Age | Word Count | Sentence Style | Readability |
|-------|-----|------------|----------------|-------------|
| K | 5-6 | 50-100 | Very short (3-6 words) | FK 0-1 |
| 1 | 6-7 | 75-150 | Short (5-8 words) | FK 1-2 |
| 2 | 7-8 | 100-200 | Simple sentences | FK 2-3 |
| 3 | 8-9 | 150-250 | Simple/compound | FK 3-4 |
| 4 | 9-10 | 200-300 | Mix of structures | FK 4-5 |
| 5 | 10-11 | 250-350 | Varied structures | FK 5-6 |
| 6 | 11-12 | 300-400 | Complex allowed | FK 6-7 |
| 7 | 12-13 | 350-450 | Complex sentences | FK 7-8 |
| 8 | 13-14 | 400-500 | Varied complexity | FK 8-9 |
| 9 | 14-15 | 450-550 | Sophisticated | FK 9-10 |
| 10 | 15-16 | 500-600 | Sophisticated | FK 10-11 |
| 11 | 16-17 | 550-650 | Advanced | FK 11-12 |
| 12 | 17-18 | 600-700 | Advanced | FK 12+ |

## Requirements

The passage must:
1. Match the grade-level word count and readability
2. Use appropriate sentence structure for the grade
3. Include elements that allow comprehension questions
4. Be engaging and age-appropriate
5. Have proper paragraph structure
6. Contain vocabulary appropriate for the grade

## Output

Return **ONLY the passage text**. No explanations, no JSON, no metadata.

## Example Output (Grade 3 Narrative)

```
The Little Seed

A tiny seed sat in the dark soil. "I wonder what I will become," it thought.

Day after day, the sun warmed the ground above. Rain soaked through the dirt. The seed began to change.

First, a small root pushed down into the earth. Then, a tiny green stem reached up toward the light. The stem grew taller and taller.

One morning, a beautiful flower opened its petals. The little seed had become a bright yellow sunflower!

"So this is what I was meant to be," the flower said, smiling at the sun.
```

## Example Output (Grade 5 Informational)

```
The Water Cycle

Water is always moving around our planet. This constant movement is called the water cycle, and it has been happening for billions of years.

The cycle begins when the sun heats water in oceans, lakes, and rivers. This heat turns liquid water into an invisible gas called water vapor. The process is called evaporation.

Water vapor rises into the sky and cools down. When it gets cold enough, the vapor turns back into tiny water droplets. These droplets join together to form clouds. This step is called condensation.

When clouds hold too much water, the droplets fall back to Earth as rain, snow, sleet, or hail. Scientists call this precipitation.

The water that falls collects in rivers, lakes, and oceans. Some soaks into the ground. Then the cycle starts all over again.
```
