---
name: populate-curriculum
description: Generate Assessment Boundaries and Common Misconceptions for ELA standards and update curriculum.md. Use this skill when curriculum data is missing or needs to be populated.
---

# Populate Curriculum Skill

This skill generates Assessment Boundaries and Common Misconceptions for ELA standards, then updates the curriculum file with the generated content.

## Purpose

When a standard in the curriculum file has empty Assessment Boundaries or Common Misconceptions (marked as `*None specified*`), this skill generates appropriate content based on the standard description. The generated content is then saved back to the curriculum file, ensuring that future requests for the same standard will reuse the same boundaries and misconceptions.

## When to Use

**Use this skill when:**
- A standard has `*None specified*` for Assessment Boundaries
- A standard has `*None specified*` for Common Misconceptions
- You need to populate curriculum data before generating MCQs
- You want to ensure curriculum data exists for a standard

## Input Schema

You receive a request with:

```json
{
  "standard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "standard_description": "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences.",
  "force_regenerate": false
}
```

- `standard_id`: The standard ID to populate
- `standard_description`: The standard description (for context)
- `force_regenerate`: If true, regenerate even if data exists (default: false)

## Output Schema

Return a JSON object:

```json
{
  "success": true,
  "assessment_boundaries": "Assessment should focus on...",
  "common_misconceptions": [
    "Students may confuse...",
    "Students often think...",
    "..."
  ],
  "updated": true
}
```

## Assessment Boundaries Guidelines

**IMPORTANT FORMAT**: Assessment Boundaries must be:
- **1-3 bullet points only** (concise, not lengthy paragraphs)
- Each bullet starts with `* ` (asterisk + space)
- Focus on what IS and is NOT assessed in one concise statement per bullet
- Match the original curriculum.md format

**Example (correct format):**
```
* Assessment is limited to identifying and explaining the function of nouns, pronouns, verbs, adjectives, and adverbs in simple sentences with grade-appropriate vocabulary. Non-defining attributes such as sentence position should not factor into classification.
* Students should identify parts of speech in sentences with straightforward word order. Complex or compound-complex sentences with multiple clauses are out of scope.
```

**BAD format (do NOT use):**
```
Assessment should focus on...

Assessment is restricted to:
- Item 1
- Item 2

Assessment should NOT include:
- Item 1
```

The format must match existing entries in curriculum.md which use simple bullet points.

## Common Misconceptions Guidelines

**IMPORTANT FORMAT**: Common Misconceptions must be:
- **3-5 bullet points** (concise statements)
- Each bullet starts with `* ` (asterisk + space)
- One misconception per bullet
- Specific and actionable for creating MCQ distractors

**Example (correct format):**
```
* Students may confuse adjectives with adverbs, thinking any descriptive word is an adjective (e.g., identifying "quickly" as an adjective).
* Students often think that verbs only show physical action and fail to recognize linking verbs (is, are, was, were) as verbs.
* Students may believe that the position of a word determines its part of speech, rather than its function in the sentence.
* Students might incorrectly believe that all adverbs end in -ly, missing common adverbs like "fast," "well," and "here."
```

Each misconception should be:
- Specific enough to create a distractor from it
- Based on typical Grade 3 student thinking
- Actionable for question design

## Workflow

1. **Check if data exists**: Read `curriculum.md` and check if Assessment Boundaries and Common Misconceptions are already populated
2. **If missing, generate**:
   - Use the standard description to understand the learning objective
   - Generate appropriate Assessment Boundaries
   - Generate 3-5 Common Misconceptions
3. **Update curriculum.md**: Write the generated content to the file, replacing `*None specified*`
4. **Return results**: Provide the generated content in the response

## File Structure

The curriculum.md file uses this format:

```
Standard ID: CCSS.ELA-LITERACY.L.3.1.A
Standard Description: Explain the function of nouns...

Assessment Boundaries:
*None specified*  ← Replace this

Common Misconceptions:
*None specified*  ← Replace this
```

After population:

```
Assessment Boundaries:
* Assessment is limited to identifying basic parts of speech in simple sentences. Complex sentence structures and advanced grammatical concepts are out of scope.
* Students should explain functions in general terms (e.g., "verbs show action"). Technical terminology beyond the five basic parts of speech is not assessed.

Common Misconceptions:
* Students may confuse adjectives with adverbs, thinking any descriptive word is an adjective.
* Students often think that verbs only show physical action, missing linking verbs.
* Students may believe word position determines part of speech, rather than function.
```

## Critical Rules

- **Consistency**: Once you've populated a standard, always reuse the same boundaries and misconceptions for that standard
- **Grade-appropriate**: All generated content must be suitable for Grade 3 students
- **Actionable**: Misconceptions should be specific enough to create meaningful MCQ distractors from them
- **Specific**: Avoid vague or generic statements - be concrete about what students misunderstand
- **Update the file**: Always save the generated content back to the curriculum file

## Example

**Input:**
```json
{
  "standard_id": "CCSS.ELA-LITERACY.L.3.1.A",
  "standard_description": "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences."
}
```

**Process:**
1. Check curriculum.md - find entry with Standard ID: CCSS.ELA-LITERACY.L.3.1.A
2. See that Assessment Boundaries and Common Misconceptions are `*None specified*`
3. Generate appropriate content based on the standard description
4. Update curriculum.md with generated content
5. Return the generated content

**Output:**
```json
{
  "success": true,
  "assessment_boundaries": "Assessment should focus on...",
  "common_misconceptions": [
    "Students may confuse adjectives with adverbs...",
    "Students often think that all words ending in -ly are adverbs...",
    "..."
  ],
  "updated": true
}
```
