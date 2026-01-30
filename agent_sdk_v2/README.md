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
│    ✓ Reads reference files (passage-guidelines.md, grammar-rules.md)        │
│    ✓ Calls tools (Skill, Read) as needed                                    │
│    ✓ Generates the final output                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Point:** Claude (the AI model) makes all decisions - which skill to use, when to read reference files, and how to generate output. This is called **"Model-invoked"** behavior.

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
│        • prepare-curriculum-batch: "Populate curriculum data..."            │
│                                                                             │
│  Claude thinks:                                                             │
│    1. "This is about ELA questions → ela-question-generation matches"       │
│    2. Invokes Skill tool → reads ela-question-generation/SKILL.md          │
│    3. Reads SKILL.md: "RL.* requires passage = YES"                        │
│    4. Reads reference/passage-guidelines.md for passage instructions        │
│    5. Generates passage inline following guidelines                         │
│    6. Creates question based on passage                                     │
│    7. Outputs final JSON                                                    │
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
│     - Sees: "RL.* requires passage = YES"                                  │
│     - Reads reference/passage-guidelines.md (a reference file, NOT a skill)│
│                              ↓                                              │
│  CLAUDE generates passage inline                                            │
│     - RL.* → narrative style (story, fable)                                │
│     - RI.* → informational style (article, explanatory)                    │
│                              ↓                                              │
│  CLAUDE continues to generate question                                      │
│     - Creates passage-based comprehension question                          │
│     - Returns JSON with passage + question                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### W.* Standards (Scenario-Based)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              WORKFLOW FOR WRITING STANDARDS (W.*)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  IMPORTANT: W.* standards are performance-based                             │
│                                                                             │
│  ✗ BAD:  "Writing helps you build your _______." (vocabulary recall)       │
│  ✓ GOOD: "Read this draft. Which revision improves...?" (scenario-based)   │
│                                                                             │
│  For MCQ/MSQ:                                                               │
│    - Provide a writing scenario or student draft                            │
│    - Ask about revisions, organization, transitions, etc.                   │
│                                                                             │
│  For Fill-in:                                                               │
│    - MUST be scenario-based with word bank                                  │
│    - Example: "Which transition connects these ideas? (choices: ...)"      │
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
│     │ prepare-curriculum-batch:                                    │        │
│     │   "Populate curriculum data..."                             │        │
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
│   │       ├── fill-in-examples.md      # Fill-in question examples
│   │       ├── grammar-rules.md         # Grammar rules for L.* standards
│   │       └── passage-guidelines.md    # Passage generation guidelines (for RL/RI)
│   └── prepare-curriculum-batch/        # Orchestrator: detect + populate
│       └── SKILL.md
├── scripts/                             # Utility scripts
│   ├── append_missing_curriculum.py     # Step 1: Append standard blocks
│   ├── populate_curriculum_direct.py    # Step 2: Fill empty fields (Direct API)
│   ├── prepare_curriculum_skill.py      # Step 2 alt: Fill via SDK skill
│   ├── test_random_sample.py            # Test pipeline on random samples
│   ├── test_cloud_endpoint.py           # Test deployed cloud endpoint
│   ├── evaluate_batch.py                # Evaluate generated questions
│   ├── generate_batch.py                # Batch question generation
│   └── debug_format.py                  # Debug output format issues
├── src/
│   ├── agentic_pipeline_sdk.py          # SDK implementation
│   └── main.py                          # API + CLI
├── outputs/                             # Generated outputs (gitignored)
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
| `/generate` | POST | Generate ELA question |
| `/skills` | GET | List available skills |
| `/` | GET | Health check |

## CLI Commands

```bash
# Test question generation
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'

# Populate curriculum.md locally (pre-deploy step)
python src/main.py --populate-curriculum '{"standard_id":"CCSS.ELA-LITERACY.L.3.1.A","standard_description":"...","grade":"3"}'

# Test with RL standard (will generate passage first)
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.RL.3.1"}'

# Start API server
python src/main.py --serve

# List available skills
python src/main.py --list-skills
```

## Skills

### Generation Skills (Runtime)

There is **only 1 skill** used during question generation:

| Skill | Description | Triggered When |
|-------|-------------|----------------|
| `ela-question-generation` | Generates MCQ, MSQ, Fill-in questions | Every ELA question request |

**Reference files** used by this skill (NOT separate skills):

| Reference File | Purpose |
|----------------|---------|
| `reference/curriculum.md` | Pre-populated curriculum data for all standards |
| `reference/passage-guidelines.md` | Instructions for generating RL/RI passages |
| `reference/fill-in-examples.md` | Example formats for fill-in questions |
| `reference/grammar-rules.md` | Grammar rules for L.* (Language) standards |

**Note:** 
- Curriculum data is **pre-fetched by Python** from `curriculum.md` (not a skill call)
- Reference files are read by Claude as needed, but they are NOT separate skills

### Preparation Skills (One-time Setup)

These skills are used **only during curriculum preparation**, not during question generation:

| Skill | Description | When Used |
|-------|-------------|-----------|
| `prepare-curriculum-batch` | Orchestrator: scans curriculum.md, detects `*None specified*`, populates | Run via `prepare_curriculum_skill.py` |

### Skill Usage Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SKILL USAGE BY PHASE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PREPARATION PHASE (one-time, before deployment):                          │
│  ───────────────────────────────────────────────                            │
│    Skills used:                                                             │
│      • prepare-curriculum-batch  → detects + fills *None specified*        │
│                                                                             │
│    Output: curriculum.md with complete Learning Objectives,                 │
│            Assessment Boundaries, Common Misconceptions                     │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  GENERATION PHASE (runtime, every request):                                 │
│  ──────────────────────────────────────────                                 │
│    Skills used:                                                             │
│      • ela-question-generation   → generates MCQ/MSQ/Fill-in               │
│                                                                             │
│    Reference files (NOT separate skills):                                   │
│      • reference/passage-guidelines.md → RL/RI passage generation          │
│      • reference/fill-in-examples.md   → Fill-in question examples         │
│      • reference/grammar-rules.md      → Grammar rules for L.* standards   │
│                                                                             │
│    Curriculum: PRE-FETCHED by Python (not a skill call!)                   │
│      → lookup_curriculum() extracts ~30 lines from curriculum.md           │
│      → Included directly in prompt sent to SDK                              │
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
| `test_random_sample.py` | Test pipeline on random N samples from benchmarks | `python scripts/test_random_sample.py --sample-size 100` |
| `test_cloud_endpoint.py` | Test the deployed cloud endpoint | `python scripts/test_cloud_endpoint.py` |
| `evaluate_batch.py` | Evaluate generated questions using InceptBench | `python scripts/evaluate_batch.py -i outputs/results.json` |
| `generate_batch.py` | Batch generate from benchmark file | `python scripts/generate_batch.py --limit 10` |
| `debug_format.py` | Debug output format issues | `python scripts/debug_format.py outputs/results.json` |

### Script Options

```bash
# Curriculum Preparation
python scripts/append_missing_curriculum.py --dry-run          # Preview what would be appended
python scripts/populate_curriculum_direct.py --limit 10        # Populate first 10 only
python scripts/populate_curriculum_direct.py --delay 1.0       # 1s delay between API calls

# Testing
python scripts/test_random_sample.py --dry-run                 # Show sample composition only
python scripts/test_random_sample.py --sample-size 100         # Generate 100 random samples
python scripts/test_random_sample.py --save-sample data/sample.jsonl  # Save sample for reuse

# Evaluation
python scripts/evaluate_batch.py -i outputs/sample_100_results.json   # Evaluate results
python scripts/evaluate_batch.py --concurrency 20              # Parallel evaluation (20 workers)
python scripts/evaluate_batch.py --show-eval                   # Show detailed evaluation JSON

# Cloud Testing
python scripts/test_cloud_endpoint.py                          # Test deployed endpoint
```

## Reference

- [Agent Skills in the SDK](https://platform.claude.com/docs/en/agent-sdk/skills)
- [Agent Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
