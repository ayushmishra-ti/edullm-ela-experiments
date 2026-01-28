# ELA Question Generation - Claude Agent SDK (Skills)

Generate ELA questions using the Claude Agent SDK with Skills.

## How It Works

```
User Request → SDK → Claude (discovers & invokes skill) → JSON Response
```

1. **Skills** are defined in `.claude/skills/` as `SKILL.md` files
2. **SDK** discovers skills automatically when `setting_sources=["user", "project"]`
3. **Claude** reads the prompt, picks the relevant skill, and generates output

## Who Decides What? (Decision Flow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DECISION FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  OUR CODE (agentic_pipeline_sdk.py):                                        │
│    ✗ Does NOT decide which skill to use                                     │
│    ✗ Does NOT load SKILL.md manually                                        │
│    ✓ Only configures: cwd, setting_sources, allowed_tools                   │
│    ✓ Only sends the prompt                                                  │
│                                                                             │
│  SDK:                                                                       │
│    ✓ Discovers skills in .claude/skills/                                    │
│    ✓ Extracts skill descriptions (from YAML frontmatter)                    │
│    ✓ Passes skill list to Claude                                            │
│    ✓ Executes tool calls that Claude requests                               │
│    ✗ Does NOT decide which skill to use                                     │
│                                                                             │
│  CLAUDE (the AI model):                                                     │
│    ✓ Reads the prompt                                                       │
│    ✓ Sees available skills and their descriptions                           │
│    ✓ DECIDES: "ela-question-generation matches this request"                │
│    ✓ DECIDES: "This is RL.*, I need generate-passage first"                 │
│    ✓ Calls tools (Skill, Read) as needed                                    │
│    ✓ Generates the final output                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Point:** Claude (the AI model) makes all decisions - which skill to use, when to call another skill, and how to generate output. This is called **"Model-invoked"** behavior.

## Claude's Decision Process (Example)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXAMPLE: Claude's Internal Decision Process               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Claude receives:                                                           │
│    - Prompt: "Generate an ELA MCQ for CCSS.ELA-LITERACY.RL.3.1"            │
│    - Available skills:                                                      │
│        • ela-question-generation: "Generate K-12 ELA assessment questions." │
│        • generate-passage: "Generate grade-appropriate reading passages."   │
│        • populate-curriculum: "Generate curriculum data..."                 │
│                                                                             │
│  Claude thinks:                                                             │
│    1. "This is about ELA questions → ela-question-generation matches"       │
│    2. Invokes Skill tool → reads ela-question-generation/SKILL.md          │
│    3. Reads SKILL.md: "RL.* requires passage = YES"                        │
│    4. "I need a passage first → generate-passage matches"                   │
│    5. Invokes Skill tool → reads generate-passage/SKILL.md                 │
│    6. Generates passage following instructions                              │
│    7. Returns to question generation with the passage                       │
│    8. Outputs final JSON                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Old Approach | SDK Skills Approach |
|--------------|---------------------|
| Python code decides flow | **Claude decides flow** |
| Hardcoded if/else logic | Claude reads instructions |
| Change code to change behavior | Change SKILL.md to change behavior |

## Workflows

### Curriculum Preparation (Pre-requisite)

Before running question generation, ensure `curriculum.md` has complete data for all standards. This is a **one-time setup** or run whenever new standards are added.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CURRICULUM PREPARATION WORKFLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  STEP 1: Append Missing Standards                                          │
│  ─────────────────────────────────                                          │
│    Script: scripts/append_missing_curriculum.py                            │
│    Purpose: Extract standard blocks from source curriculum and append       │
│             to curriculum.md (structure only, fields are *None specified*) │
│                                                                             │
│    $ python scripts/append_missing_curriculum.py --dry-run                 │
│    $ python scripts/append_missing_curriculum.py                           │
│                              ↓                                              │
│  STEP 2: Populate Empty Fields                                             │
│  ─────────────────────────────                                              │
│    Script: scripts/populate_curriculum_direct.py                           │
│    Purpose: Fill *None specified* sections with AI-generated content       │
│             - Learning Objectives                                           │
│             - Assessment Boundaries                                         │
│             - Common Misconceptions                                         │
│                                                                             │
│    $ python scripts/populate_curriculum_direct.py --dry-run                │
│    $ python scripts/populate_curriculum_direct.py                          │
│                              ↓                                              │
│  RESULT: curriculum.md is complete and ready for question generation       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Alternative: Skill-Based Populate (via SDK)**

```bash
# Uses prepare-curriculum-batch skill - Claude detects and populates autonomously
python scripts/prepare_curriculum_skill.py --limit 10
```

| Script | Approach | Best For |
|--------|----------|----------|
| `populate_curriculum_direct.py` | Direct Anthropic API | Large batches (300+), reliability |
| `prepare_curriculum_skill.py` | SDK + Skill | Small batches, seeing Claude's reasoning |

### Question Generation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        QUESTION GENERATION WORKFLOW                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. USER sends request                                                      │
│     POST /generate {"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}         │
│                              ↓                                              │
│  2. SDK receives request, builds prompt                                     │
│     "Generate an ELA MCQ for L.3.1.A..."                                   │
│                              ↓                                              │
│  3. SDK calls: query(prompt=..., options=ClaudeAgentOptions(...))          │
│     - cwd: project directory                                                │
│     - setting_sources: ["user", "project"]  ← Discovers skills              │
│     - allowed_tools: ["Skill", "Read"]      ← Enables skill invocation      │
│                              ↓                                              │
│  4. CLAUDE receives prompt + discovered skills                              │
│     - Sees skill descriptions from .claude/skills/*/SKILL.md               │
│     - Decides: "ela-question-generation matches this request"              │
│     - Invokes the skill                                                     │
│                              ↓                                              │
│  5. CLAUDE reads ela-question-generation/SKILL.md                          │
│     - Follows instructions for MCQ format                                   │
│     - Checks if passage needed (L.* = NO)                                  │
│     - Generates question JSON                                               │
│                              ↓                                              │
│  6. SDK returns response to user                                            │
│     {"id": "l_3_1_a_mcq_medium_001", "content": {...}}                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### RL/RI Standards (Passage Required)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              WORKFLOW FOR READING STANDARDS (RL.* / RI.*)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Request: "Generate MCQ for CCSS.ELA-LITERACY.RL.3.1"                      │
│                              ↓                                              │
│  CLAUDE reads ela-question-generation/SKILL.md                             │
│     - Sees: "RL.* requires passage = YES, style = narrative"               │
│     - Invokes generate-passage skill first                                  │
│                              ↓                                              │
│  CLAUDE reads generate-passage/SKILL.md                                    │
│     - Generates grade-appropriate narrative passage                         │
│                              ↓                                              │
│  CLAUDE returns to ela-question-generation                                  │
│     - Creates passage-based comprehension question                          │
│     - Returns JSON with question anchored to passage                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Skill Discovery Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SKILL DISCOVERY FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SDK Startup (when query() is called):                                      │
│                                                                             │
│  1. SDK reads setting_sources=["user", "project"]                          │
│                              ↓                                              │
│  2. SDK scans directories:                                                  │
│     - Project: {cwd}/.claude/skills/*/SKILL.md                             │
│     - User: ~/.claude/skills/*/SKILL.md                                    │
│                              ↓                                              │
│  3. SDK extracts skill metadata (name, description)                        │
│     ┌─────────────────────────────────────────────────────────────┐        │
│     │ ela-question-generation:                                     │        │
│     │   "Generate K-12 ELA assessment questions..."               │        │
│     │                                                              │        │
│     │ generate-passage:                                            │        │
│     │   "Generate grade-appropriate reading passages..."          │        │
│     │                                                              │        │
│     │ populate-curriculum:                                         │        │
│     │   "Generate curriculum data..."                             │        │
│     └─────────────────────────────────────────────────────────────┘        │
│                              ↓                                              │
│  4. Claude receives prompt + skill list                                     │
│     - Claude matches prompt to skill description                            │
│     - Invokes relevant skill autonomously                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Allowed Tools Explained

```python
allowed_tools=["Skill", "Read"]
```

| Tool | Why Needed |
|------|-----------|
| `Skill` | **Required** - Enables Claude to invoke skills from `.claude/skills/` |
| `Read` | Allows Claude to read files (e.g., `curriculum.md` for context) |

**Note:** `Bash` is optional. Only add it if your SKILL.md files need to execute scripts.

## Curriculum Pre-fetching (Optimization)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CURRICULUM DATA OPTIMIZATION                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  THE PROBLEM:                                                               │
│    curriculum.md = 8,190 lines (223 standards × ~35 lines each)            │
│    Having Claude read the entire file = ~70,000 tokens = expensive         │
│                                                                             │
│  THE SOLUTION:                                                              │
│    Python pre-fetches ONLY the relevant standard's data (~30-40 lines)     │
│    This data is included directly in the prompt sent to SDK                │
│                                                                             │
│  HOW IT WORKS:                                                              │
│    1. Request comes in: "Generate MCQ for L.3.1.A"                         │
│    2. Python calls lookup_curriculum("CCSS.ELA-LITERACY.L.3.1.A")          │
│    3. Function extracts ~30 lines for that standard                         │
│    4. Curriculum data included in prompt to SDK                             │
│    5. Claude has context without reading huge file                          │
│                                                                             │
│  RESULT:                                                                    │
│    Before: 8,190 lines (~70K tokens)                                       │
│    After:  ~30 lines (~500 tokens)                                         │
│    Savings: 99% reduction in context for curriculum data                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```python
# In agentic_pipeline_sdk.py
def lookup_curriculum(standard_id: str) -> str | None:
    """Extract only the relevant ~30 lines for this standard."""
    path = _curriculum_md_path()
    content = path.read_text(encoding="utf-8")
    blocks = content.split("\n---\n")
    
    for block in blocks:
        if f"Standard ID: {standard_id}" in block:
            return block.strip()  # ~30-40 lines
    return None
```

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Add your ANTHROPIC_API_KEY

# 3. Prepare Curriculum (one-time setup)
# Step 3a: Append any missing standard blocks from source
python scripts/append_missing_curriculum.py --dry-run
python scripts/append_missing_curriculum.py

# Step 3b: Populate empty fields (Learning Objectives, etc.)
python scripts/populate_curriculum_direct.py --dry-run
python scripts/populate_curriculum_direct.py

# 4. Test question generation
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'

# 5. Test on random sample from benchmarks
python scripts/test_random_sample.py --sample-size 10 --seed 42

# 6. Start API server
python src/main.py --serve
```

## Project Structure

```
agent_sdk_v2/
├── .claude/skills/                      # Skills (SDK discovers these)
│   ├── ela-question-generation/         # Main skill - question generation
│   │   ├── SKILL.md
│   │   └── reference/
│   │       ├── curriculum.md            # Curriculum data (pre-populated)
│   │       └── fill-in-examples.md      # Fill-in question examples
│   ├── generate-passage/                # Passage generation for RL/RI
│   │   └── SKILL.md
│   └── prepare-curriculum-batch/        # Curriculum prep (optional, skill-based)
│       └── SKILL.md
├── scripts/                             # Utility scripts
│   ├── append_missing_curriculum.py     # Step 1: Append standard blocks
│   ├── populate_curriculum_direct.py    # Step 2: Fill empty fields (Direct API)
│   ├── prepare_curriculum_skill.py      # Step 2 alt: Fill via SDK skill
│   ├── test_random_sample.py            # Test pipeline on random samples
│   └── generate_batch.py                # Batch question generation
├── src/
│   ├── agentic_pipeline_sdk.py          # SDK implementation
│   └── main.py                          # API + CLI
├── data/                                # Benchmark files
│   ├── grade-2-ela-benchmark.jsonl
│   ├── grade-5-ela-benchmark.jsonl
│   ├── grade-6-ela-benchmark.jsonl
│   └── grade-8-ela-benchmark.jsonl
└── requirements.txt
```

## Core Code

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    cwd="/path/to/project",              # Contains .claude/skills/
    setting_sources=["user", "project"], # REQUIRED: Enables skill discovery
    allowed_tools=["Skill", "Read"]      # REQUIRED: Skill tool + Read for files
)

async for message in query(prompt="Generate an ELA MCQ...", options=options):
    print(message)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/generate` | POST | Generate ELA question (SDK Skills) |
| `/` | GET | Health check |

**Note:** This deploys as a NEW separate service (`inceptagentic-skill-mcq-v2`). The existing service (`inceptagentic-skill-mcq`) remains untouched.

## CLI Commands

```bash
# Test question generation
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'

# Test with RL standard (will generate passage first)
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.RL.3.1"}'

# Start API server
python src/main.py --serve
```

## Skills

### Generation Skills (Runtime)

These are the **only 2 skills** used during question generation:

| Skill | Description | Triggered When |
|-------|-------------|----------------|
| `ela-question-generation` | Generates MCQ, MSQ, Fill-in questions | Every ELA question request |
| `generate-passage` | Creates reading passages | RL.* or RI.* standards only |

**Note:** Curriculum data is **NOT** fetched via a skill at runtime. It is **pre-fetched by Python** from `curriculum.md` and included in the prompt to reduce token usage.

### Preparation Skills (One-time Setup)

| Skill | Description | When Used |
|-------|-------------|-----------|
| `prepare-curriculum-batch` | Scans curriculum.md, detects `*None specified*`, populates | Run via `prepare_curriculum_skill.py` |

### How Claude Discovers and Chooses Skills

**We don't explicitly specify which skill to use in code.** Claude decides autonomously.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HOW SKILL SELECTION WORKS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CODE (agentic_pipeline_sdk.py):                                           │
│                                                                             │
│    options = ClaudeAgentOptions(                                           │
│        cwd=str(ROOT),                        # Points to agent_sdk_v2/     │
│        setting_sources=["user", "project"], # Discovers ALL skills        │
│        allowed_tools=["Skill", "Read"],     # Enables skill invocation    │
│    )                                                                        │
│                                                                             │
│  SDK STARTUP:                                                               │
│    1. Scans: agent_sdk_v2/.claude/skills/*/SKILL.md                        │
│    2. Extracts ALL skill descriptions from YAML frontmatter                │
│    3. Passes skill list to Claude                                          │
│                                                                             │
│  CLAUDE RECEIVES:                                                           │
│    - Prompt: "Generate an ELA MCQ for L.3.1.A..."                          │
│    - Available skills:                                                      │
│        • ela-question-generation: "Generate K-12 ELA assessment..."        │
│        • generate-passage: "Generate grade-appropriate passages..."        │
│        • prepare-curriculum-batch: "Scan curriculum.md for missing..."     │
│                                                                             │
│  CLAUDE DECIDES:                                                            │
│    "ela-question-generation matches this request" ← Based on description   │
│                                                                             │
│  WHY OTHER SKILLS AREN'T USED:                                              │
│    • prepare-curriculum-batch → description doesn't match "generate MCQ"   │
│    • Claude only invokes skills whose descriptions match the prompt        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Skill Usage by Phase

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SKILL USAGE BY PHASE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PREPARATION PHASE (one-time, before deployment):                          │
│  ───────────────────────────────────────────────                            │
│    Option A: Direct API (recommended for large batches)                    │
│      $ python scripts/populate_curriculum_direct.py                        │
│      → No skills involved, direct Anthropic API calls                      │
│                                                                             │
│    Option B: Skill-based                                                    │
│      $ python scripts/prepare_curriculum_skill.py                          │
│      → Uses: prepare-curriculum-batch skill                                │
│                                                                             │
│    Output: curriculum.md with complete Learning Objectives,                 │
│            Assessment Boundaries, Common Misconceptions                     │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  GENERATION PHASE (runtime, every request):                                 │
│  ──────────────────────────────────────────                                 │
│    Skills used (Claude chooses based on prompt):                           │
│      • ela-question-generation   → generates MCQ/MSQ/Fill-in               │
│      • generate-passage          → generates passage (RL.*/RI.* only)      │
│                                                                             │
│    Curriculum: PRE-FETCHED by Python (not a skill call!)                   │
│      → lookup_curriculum() extracts ~30 lines from curriculum.md           │
│      → Included directly in prompt sent to SDK                              │
│      → Claude never reads curriculum.md during generation                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Curriculum is Pre-fetched (Not a Skill)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY PRE-FETCH CURRICULUM DATA?                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  curriculum.md = 20,000+ lines (500+ standards)                            │
│                                                                             │
│  ✗ BAD: Claude reads entire file via skill → ~200K tokens → expensive      │
│  ✓ GOOD: Python extracts ~30 lines → ~500 tokens → 99% savings             │
│                                                                             │
│  The lookup happens BEFORE calling the SDK:                                 │
│                                                                             │
│    curriculum_context = lookup_curriculum(substandard_id)  # Python        │
│    prompt = f"...{curriculum_context}..."                  # Include in prompt
│    query(prompt=prompt, options=options)                   # Send to SDK    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Scripts

### Curriculum Preparation Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `append_missing_curriculum.py` | Append standard blocks from source curriculum | `python scripts/append_missing_curriculum.py` |
| `populate_curriculum_direct.py` | Fill `*None specified*` fields via direct API | `python scripts/populate_curriculum_direct.py` |
| `prepare_curriculum_skill.py` | Fill fields via SDK skill (Claude decides) | `python scripts/prepare_curriculum_skill.py` |

### Testing & Generation Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `test_random_sample.py` | Test pipeline on random N samples from benchmarks | `python scripts/test_random_sample.py -n 200 --seed 42` |
| `generate_batch.py` | Batch generate from benchmark file | `python scripts/generate_batch.py --limit 10` |

### Script Options

```bash
# Curriculum Preparation
python scripts/append_missing_curriculum.py --dry-run          # Preview what would be appended
python scripts/populate_curriculum_direct.py --limit 10        # Populate first 10 only
python scripts/populate_curriculum_direct.py --delay 1.0       # 1s delay between API calls

# Testing
python scripts/test_random_sample.py --dry-run                 # Show sample composition only
python scripts/test_random_sample.py --sample-size 50 --seed 42  # Reproducible 50 samples
python scripts/test_random_sample.py --save-sample data/sample.jsonl  # Save sample for reuse
```

## Reference

- [Agent Skills in the SDK](https://platform.claude.com/docs/en/agent-sdk/skills)
- [Agent Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
