---
name: prepare-curriculum-batch
description: Scan curriculum.md for standards with missing Learning Objectives, Assessment Boundaries, or Common Misconceptions (marked as *None specified*), then generate and fill those fields. Use this BEFORE batch question generation to ensure all curriculum data is complete.
---

# Prepare Curriculum Batch

Scan `curriculum.md` and populate any missing curriculum fields before question generation.

## SDK Usage

To invoke this skill via the Claude Agent SDK:

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    cwd="/path/to/agent_sdk_v2",
    setting_sources=["user", "project"],
    allowed_tools=["Skill", "Read", "Write", "Bash"]  # Required tools
)

async for message in query(
    prompt="Use the prepare-curriculum-batch skill to populate missing curriculum fields",
    options=options
):
    print(message)
```

Or run the invocation script:

```bash
cd agent_sdk_v2
python scripts/prepare_curriculum_skill.py
python scripts/prepare_curriculum_skill.py --limit 10
python scripts/prepare_curriculum_skill.py --verbose
```

## When to Use

- Before running batch question generation
- When you see `*None specified*` in curriculum blocks
- After appending new standards to curriculum.md
- User asks to "prepare curriculum", "populate missing fields", or "fill curriculum gaps"

## Workflow

### Step 1: Read curriculum.md

Read the curriculum file at:
```
.claude/skills/ela-question-generation/reference/curriculum.md
```

### Step 2: Identify Blocks Needing Population

Scan for curriculum blocks (separated by `---`) that have ANY of these markers:

```
Learning Objectives:
*None specified*

Assessment Boundaries:
*None specified*

Common Misconceptions:
*None specified*
```

A block needs population if ANY of these three sections contains `*None specified*`.

### Step 3: Extract Standard Info

For each block needing population, extract:
- `Standard ID:` line → the standard identifier
- `Standard Description:` line → what the standard covers
- `Course:` line → contains grade info (e.g., "2nd Grade", "6th Grade")

### Step 4: Generate Curriculum Data

For each standard needing population, generate:

#### Learning Objectives (2-4 bullet points)
- Student-facing, measurable outcomes
- Use action verbs: identify, explain, choose, revise, apply, distinguish
- Must reflect the standard description exactly

#### Assessment Boundaries (1-3 bullet points)
- What IS and is NOT assessed
- Grade-appropriate scope
- Clear limits (e.g., "Limited to simple sentences")

#### Common Misconceptions (3-5 bullet points)
- Specific student errors (not vague "students get confused")
- Include examples where helpful
- These become MCQ distractors

### Step 5: Update curriculum.md

For each standard, replace the `*None specified*` sections with the generated content.

**Format for each section:**
```
Learning Objectives:
* Students can [objective 1]
* Students can [objective 2]
* Students can [objective 3]

Assessment Boundaries:
* [boundary 1]
* [boundary 2]

Common Misconceptions:
* [misconception 1]
* [misconception 2]
* [misconception 3]
```

### Step 6: Report Results

After updating, report:
- How many standards were found needing population
- How many were successfully populated
- List of Standard IDs that were updated

## Example

**Before (in curriculum.md):**
```
Standard ID: CCSS.ELA-LITERACY.L.2.1.A
Standard Description: Use collective nouns (e.g., group).

Key Concepts:
*None specified*

Learning Objectives:
*None specified*

Assessment Boundaries:
*None specified*

Common Misconceptions:
*None specified*

Difficulty Definitions:
* Easy:
  <unspecified>
```

**After your update:**
```
Standard ID: CCSS.ELA-LITERACY.L.2.1.A
Standard Description: Use collective nouns (e.g., group).

Key Concepts:
*None specified*

Learning Objectives:
* Students can identify collective nouns in sentences
* Students can use collective nouns correctly to name groups of people, animals, or things
* Students can distinguish between collective nouns and regular plural nouns

Assessment Boundaries:
* Assessment is limited to common collective nouns appropriate for 2nd grade (e.g., group, team, family, class, herd, flock)
* Students should recognize and use collective nouns in simple sentences only
* Does not include less common or abstract collective nouns

Common Misconceptions:
* Students may confuse collective nouns with plural nouns (e.g., thinking "dogs" is a collective noun)
* Students might not understand that collective nouns are singular (e.g., "The team is" not "The team are")
* Students may think collective nouns only refer to people, missing animal groups (herd, flock, pack)
* Students might create incorrect collective nouns by adding "group of" to everything

Difficulty Definitions:
* Easy:
  <unspecified>
```

## Quality Guidelines by Standard Type

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

## Processing Limits

When processing many standards:
- Process in batches of 10-20 standards at a time
- Save after each batch to avoid losing work
- Report progress as you go

## Critical Rules

1. **Preserve existing content** - Only replace `*None specified*` sections
2. **Keep block structure** - Don't change Standard ID, Description, Key Concepts, or Difficulty Definitions
3. **Use bullet format** - Each item starts with `* `
4. **Grade-appropriate** - Match complexity to the grade level in the standard
5. **Save frequently** - Write updates to curriculum.md after each batch
