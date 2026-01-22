# Test Commands for MCQ Generation Pipelines

## Prerequisites

1. Set up `.env` file with:
   ```bash
   ANTHROPIC_API_KEY=your_key_here
   # Optional (uses skill files if not set):
   CCAPI_ELA_MCQ_SKILL_ID=your_skill_id
   CCAPI_POPULATE_CURRICULUM_SKILL_ID=your_skill_id
   # Optional (only needed for evaluation):
   INCEPT_API_KEY=your_key_here
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## CCAPI Pipeline (Parent Folder) - Python Orchestrated

### Basic Generation (No Curriculum Context)
```bash
# Generate 5 MCQs without curriculum context
python scripts/generate_batch.py --limit 5

# Generate 5 MCQs with custom output
python scripts/generate_batch.py --limit 5 -o outputs/test_basic.json
```

### With Curriculum Context
```bash
# Generate 5 MCQs with curriculum context (looks up and populates curriculum.md)
python scripts/generate_batch.py --limit 5 --use-curriculum

# With custom output
python scripts/generate_batch.py --limit 5 --use-curriculum -o outputs/test_curriculum.json
```

### With Evaluation
```bash
# Generate 5 MCQs and evaluate with InceptBench
python scripts/generate_batch.py --limit 5 --evaluation

# With curriculum context + evaluation
python scripts/generate_batch.py --limit 5 --use-curriculum --evaluation

# Using --evaluate (same as --evaluation)
python scripts/generate_batch.py --limit 5 --evaluate
```

### Full Example
```bash
# Generate 10 MCQs with curriculum context, evaluate, and save to custom location
python scripts/generate_batch.py --limit 10 --use-curriculum --evaluation -o outputs/full_test.json
```

## Agentic Pipeline (option_c_agent_sdk) - Claude Decides Everything

### Basic Agentic Generation
```bash
# Generate 5 MCQs using fully agentic approach (Claude decides tool usage)
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 5

# With custom output
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 5 -o option_c_agent_sdk/outputs/test_agentic.json
```

### Simple Mode (Read/Bash tools instead of custom MCP tools)
```bash
# Use simple mode (Claude uses Read/Bash tools directly)
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 5 --simple
```

### With Custom Concurrency
```bash
# Generate with lower concurrency (default is 3 for agentic)
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 5 --concurrency 2
```

## Comparison Tests

### Test Both Approaches Side-by-Side
```bash
# 1. Test CCAPI pipeline with curriculum
python scripts/generate_batch.py --limit 3 --use-curriculum -o outputs/ccapi_curriculum.json

# 2. Test agentic pipeline
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 3 -o option_c_agent_sdk/outputs/agentic.json

# Compare the outputs
```

## Quick Test Commands

### Minimal Test (Fastest)
```bash
# CCAPI: 1 MCQ, no curriculum, no evaluation
python scripts/generate_batch.py --limit 1

# Agentic: 1 MCQ
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 1
```

### Full Feature Test
```bash
# CCAPI: 3 MCQs, with curriculum, with evaluation
python scripts/generate_batch.py --limit 3 --use-curriculum --evaluation

# Agentic: 3 MCQs (Claude handles curriculum automatically)
python option_c_agent_sdk/scripts/generate_batch_agentic.py --limit 3
```

## Troubleshooting

### If Skills API fails
- The pipeline will automatically fall back to skill files
- Make sure `skills/ela-mcq-generation/SKILL.md` exists
- Make sure `skills/populate-curriculum/SKILL.md` exists (for curriculum pipeline)

### If curriculum lookup fails
- Check that `option_c_agent_sdk/data/curriculum.md` exists
- The pipeline will auto-populate missing data on first use

### If evaluation fails
- Make sure `INCEPT_API_KEY` is set in `.env`
- Evaluation is optional - you can run without `--evaluation` flag

## Output Locations

- CCAPI pipeline: `outputs/batch_generated.json` (default)
- Agentic pipeline: `option_c_agent_sdk/outputs/batch_agentic.json` (default)
