# Option C: Claude Agent SDK Implementation (Fully Agentic)

This implementation uses the Claude Agent SDK in a **fully agentic** approach where Claude autonomously decides when to call tools (curriculum lookup, population, etc.). Unlike the parent folder's Python-orchestrated approach, Claude controls the entire workflow here.

**For Python-orchestrated approach with curriculum context + skills**, use the parent folder:
- `ccapi/src/ccapi/pipeline_with_curriculum.py` - Python orchestrates, uses Skills API or skill files
- Run with: `python scripts/generate_batch.py --use-curriculum`

## 📁 Folder Structure

```
option_c_agent_sdk/
├── README.md                    # This file (quick overview)
├── docs/                        # 📚 Documentation
│   ├── README.md               # Full documentation
│   ├── WORKFLOW.md             # Workflow diagram and process
│   ├── TEST_COMMANDS.md        # Test command reference
│   └── CURRICULUM_POPULATION_SUMMARY.md
├── src/                         # 💻 Source Code
│   ├── curriculum_lookup.py    # Curriculum parsing and lookup
│   ├── populate_curriculum.py  # Curriculum data population
│   ├── pipeline_agent_sdk.py   # DEPRECATED - Use parent folder or agentic_pipeline.py
│   ├── agentic_pipeline.py     # Fully agentic MCQ generation (Claude decides tool usage)
│   ├── agentic_tools.py         # Custom MCP tools for Claude
│   ├── save_outputs.py         # Output saving utilities
│   └── tool_curriculum_lookup.py
├── tests/                       # 🧪 Tests
│   └── test_pipeline.py        # Main test script
├── data/                        # 📊 Data Files
│   └── curriculum.md           # Grade 3 ELA curriculum
├── outputs/                     # 📤 Generated Outputs
│   └── README.md               # Output folder documentation
└── skills/                      # 🎯 Skill Definitions
    ├── ela-mcq-generation/
    └── populate-curriculum/
```

## 🚀 Quick Start

### Installation

```bash
pip install claude-agent-sdk
export ANTHROPIC_API_KEY=your-api-key
```

### Run Tests

```bash
# From ccapi root directory
python option_c_agent_sdk/tests/test_pipeline.py
```

### Usage (Fully Agentic)

```python
from option_c_agent_sdk import generate_one_agentic

request = {
    "type": "mcq",
    "grade": "3",
    "skills": {
        "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
        "substandard_description": "..."
    },
    "subject": "ela",
    "curriculum": "common core",
    "difficulty": "easy"
}

# Claude autonomously decides when to:
# 1. Call lookup_curriculum tool
# 2. Call populate_curriculum tool (if needed)
# 3. Generate the MCQ
result = await generate_one_agentic(request)
```

### Batch Generation

```bash
# From ccapi root directory
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 5
```

## 📖 Documentation

- **[Full Documentation](docs/README.md)** - Complete guide and API reference
- **[Workflow](docs/WORKFLOW.md)** - Process flow and mermaid diagrams
- **[Test Commands](docs/TEST_COMMANDS.md)** - All test commands reference
- **[Outputs](outputs/README.md)** - Output file structure

## 🔑 Key Features

- **Fully Agentic** - Claude autonomously decides when to call tools (curriculum lookup, population, etc.)
- **Custom MCP Tools** - Provides `lookup_curriculum` and `populate_curriculum` tools that Claude can call
- **No Python Orchestration** - Unlike parent folder, Python doesn't pre-fetch curriculum data
- **Automatic Curriculum Population** - When Claude detects missing data, it calls populate_curriculum tool
- **Consistent Reuse** - Once a standard's curriculum data is populated, all future questions use the same boundaries and misconceptions

## 📝 Main Components

1. **Agentic Pipeline** (`src/agentic_pipeline.py`) - Fully agentic MCQ generation (Claude decides tool usage)
2. **Agentic Tools** (`src/agentic_tools.py`) - Custom MCP tools for Claude to call
3. **Curriculum Lookup** (`src/curriculum_lookup.py`) - Parse and search curriculum.md
4. **Population** (`src/populate_curriculum.py`) - Generate missing curriculum data
5. **Outputs** (`src/save_outputs.py`) - Save results to outputs/

**Note**: `pipeline_agent_sdk.py` is deprecated. Use `agentic_pipeline.py` for fully agentic approach, or use parent folder's `pipeline_with_curriculum.py` for Python-orchestrated approach.

## 🧪 Testing

See [docs/TEST_COMMANDS.md](docs/TEST_COMMANDS.md) for all test commands.

## 📤 Outputs

Generated results are saved to `outputs/` folder. See [outputs/README.md](outputs/README.md) for details.
