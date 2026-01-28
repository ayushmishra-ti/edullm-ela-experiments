# ELA Question Generation - Claude Agent SDK (Skills)

Generate ELA questions using the Claude Agent SDK with Skills.

## How It Works

```
User Request → SDK → Claude (discovers & invokes skill) → JSON Response
```

1. **Skills** are defined in `.claude/skills/` as `SKILL.md` files
2. **SDK** discovers skills automatically when `setting_sources=["user", "project"]`
3. **Claude** reads the prompt, picks the relevant skill, and generates output

## Workflows

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

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Add your ANTHROPIC_API_KEY

# Test
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'

# Server
python src/main.py --serve
```

## Project Structure

```
agent_sdk_v2/
├── .claude/skills/                  # Skills (SDK discovers these)
│   ├── ela-question-generation/     # Main skill - question generation
│   │   └── SKILL.md
│   ├── generate-passage/            # Passage generation for RL/RI
│   │   └── SKILL.md
│   └── populate-curriculum/         # Curriculum data generation
│       └── SKILL.md
├── src/
│   ├── agentic_pipeline_sdk.py      # SDK implementation
│   └── main.py                      # API + CLI
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
| `/populate-curriculum` | POST | Generate curriculum data |
| `/skills` | GET | List available skills |
| `/` | GET | Health check |

## CLI Commands

```bash
# Test question generation
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'

# Test with RL standard (will generate passage first)
python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.RL.3.1"}'

# Start API server
python src/main.py --serve

# List available skills
python src/main.py --list-skills
```

## Skills

| Skill | Description | Triggered When |
|-------|-------------|----------------|
| `ela-question-generation` | Generates MCQ, MSQ, Fill-in questions | ELA question request |
| `generate-passage` | Creates reading passages | RL.* or RI.* standard |
| `populate-curriculum` | Generates learning objectives | Curriculum data request |

## Reference

- [Agent Skills in the SDK](https://platform.claude.com/docs/en/agent-sdk/skills)
- [Agent Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
