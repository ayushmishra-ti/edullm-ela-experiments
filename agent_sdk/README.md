# ELA Question Generation - Fully Agentic with Self-Correction

This project generates K-12 ELA questions using **Claude as the orchestrator**. Claude autonomously decides which tools to run, and can self-correct low-scoring questions based on evaluation feedback.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FULL AGENTIC PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. GENERATE (Claude orchestrates)                                          │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ Request → Claude reads SKILL.md → decides tools:                 │   │
│     │   • lookup_curriculum (check if curriculum data exists)          │   │
│     │   • populate_curriculum (if data missing, generate it)           │   │
│     │   • Generate question with full context                          │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│  2. EVALUATE (InceptBench)                                                  │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ Question → InceptBench → Full evaluation JSON                    │   │
│     │   • Overall score, dimension scores, reasoning, suggestions      │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│  3. SELF-CORRECT (Claude decides)                                           │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ Claude analyzes evaluation → decides:                            │   │
│     │   • KEEP if score >= 85%                                         │   │
│     │   • REGENERATE if score < 85% (calls regenerate_question tool)   │   │
│     │                                                                  │   │
│     │ Regeneration Subagent:                                           │   │
│     │   • Receives original + full evaluation feedback                 │   │
│     │   • Addresses ALL issues identified                              │   │
│     │   • Returns improved question                                    │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│  4. RE-EVALUATE (if regenerated)                                            │
│     ┌──────────────────────────────────────────────────────────────────┐   │
│     │ Track improvement, keep better version                           │   │
│     └──────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key difference from Python orchestration**: Claude decides everything - when to call curriculum tools, how to generate questions, AND whether to regenerate based on evaluation feedback.

## Agent Skills Structure

```
.claude/skills/
├── ela-question-generation/       # Master generation skill
│   ├── SKILL.md                   # Instructions for Claude
│   ├── scripts/                   # Executable tools
│   │   ├── lookup_curriculum.py
│   │   └── populate_curriculum.py
│   └── references/
│       └── curriculum.md          # Curriculum database
│
└── question-self-correction/      # Self-correction skill
    └── SKILL.md                   # Decision rules, regeneration instructions
```

## Workflows

### 1. Generate Only (Quick)

Generate questions without evaluation:

```bash
python scripts/generate_batch.py --limit 10
```

Output: `outputs/batch_generated.json`

### 2. Evaluate Only

Evaluate existing generated questions:

```bash
python scripts/evaluate_batch.py

# Show full evaluation JSON for each item
python scripts/evaluate_batch.py --show-eval
```

Output: `outputs/eval_results.csv`

### 3. Generate and Refine (Full Agentic Pipeline)

Generate with curriculum tools + Claude self-evaluation + regeneration:

```bash
# Random 5 from benchmark
python scripts/generate_and_refine_v2.py -n 5 -r

# Specific type only
python scripts/generate_and_refine_v2.py -n 10 -r -t mcq
```

**What happens:**
1. Claude generates question (agentic - calls `lookup_curriculum`, `populate_curriculum` as needed)
2. Claude self-assesses the question (no InceptBench call)
3. If self-assessment < 85%: Regenerate with feedback
4. Output in InceptBench format

**Key benefit:** No InceptBench calls during generation loop (fast, cheap). Run InceptBench once at the end for validation.

Output: `outputs/batch_generated.json`

**Example output:**
```
[1/5] CCSS.ELA-LITERACY.L.3.1.A_mcq_easy
  → Generating (agentic)... ✓ (tools: lookup_curriculum → populate_curriculum)
  → Self-assessing... ✓ 92.0% (confident, passed)

[2/5] CCSS.ELA-LITERACY.SL.3.1.A_msq_hard
  → Generating (agentic)... ✓ (tools: lookup_curriculum → populate_curriculum)
  → Self-assessing... ⚠ 72.0% (not confident)
      Issues: Distractor A too similar to correct answer
  → Regenerating with self-feedback... ✓ Regenerated

============================================================
Pipeline Complete (No InceptBench calls)
============================================================
Total requests:      5
Generated:           5
Below threshold:     1
Regenerated:         1
Final output count:  5

To validate with InceptBench:
  python -m inceptbench evaluate outputs/batch_generated.json
```

## Command Reference

| Script | Purpose | Example |
|--------|---------|---------|
| `generate_batch.py` | Generate questions (agentic) | `python scripts/generate_batch.py --limit 10` |
| `evaluate_batch.py` | Evaluate with InceptBench | `python scripts/evaluate_batch.py --show-eval` |
| `generate_and_refine_v2.py` | Full pipeline with self-correction | `python scripts/generate_and_refine_v2.py -n 5 -r` |

### Script Options

**generate_batch.py**
```bash
--input, -i     # Input JSONL file (default: data/grade-3-ela-benchmark.jsonl)
--output, -o    # Output JSON file (default: outputs/batch_generated.json)
--limit, -n     # Limit number of items
--type, -t      # Filter: all, mcq, msq, fill-in
--verbose, -v   # Show Claude's tool calls
```

**evaluate_batch.py**
```bash
--input, -i     # Input JSON file (default: outputs/batch_generated.json)
--output, -o    # Output CSV file (default: outputs/eval_results.csv)
--show-eval, -e # Show full evaluation JSON for each item
--debug         # Show inceptbench INFO logs
```

**generate_and_refine_v2.py**
```bash
--input, -i     # Input JSONL file
--output, -o    # Output JSON file (default: outputs/batch_generated.json)
--limit, -n     # Limit number of items
--random, -r    # Randomly sample items instead of first N
--type, -t      # Filter: all, mcq, msq, fill-in
--threshold     # Score threshold for regeneration (default: 0.85 = 85%)
--max-retries   # Max regeneration attempts per item (default: 1)
--verbose, -v   # Show detailed output
```

## Available Skills

| Skill | Description | Used By |
|-------|-------------|---------|
| `ela-question-generation` | Full question generation with curriculum tools | `generate_batch.py`, `generate_and_refine_v2.py` |
| `question-self-correction` | Self-assessment criteria & regeneration | `generate_and_refine_v2.py` |

## Manual Script Usage

```bash
# Lookup curriculum data
python .claude/skills/ela-question-generation/scripts/lookup_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A"

# Populate missing curriculum
python .claude/skills/ela-question-generation/scripts/populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.B" "Form and use regular and irregular plural nouns."
```

## Data Files

| File | Description |
|------|-------------|
| `data/grade-3-ela-benchmark.jsonl` | Input benchmark requests |
| `.claude/skills/ela-question-generation/references/curriculum.md` | Curriculum database |
| `outputs/batch_generated.json` | Generated questions |
| `outputs/refined_generated.json` | Self-corrected questions |
| `outputs/eval_results.csv` | Evaluation results |

## Output Formats

### Generated Question (MCQ)
```json
{
  "id": "l_3_1_a_mcq_easy_001",
  "content": {
    "answer": "B",
    "question": "Which word in this sentence is a noun?",
    "image_url": [],
    "answer_options": [
      {"key": "A", "text": "sleeps"},
      {"key": "B", "text": "cat"},
      {"key": "C", "text": "soft"},
      {"key": "D", "text": "on"}
    ],
    "answer_explanation": "A noun names a person, place, thing, or animal..."
  }
}
```

### Fill-in Question (NO answer_options)
```json
{
  "id": "l_3_1_d_fillin_easy_001",
  "content": {
    "answer": "ran",
    "question": "Yesterday, I ______ to the store. (Write the past tense of 'run')",
    "image_url": [],
    "additional_details": "CCSS.ELA-LITERACY.L.3.1.D",
    "answer_explanation": "The past tense of 'run' is 'ran'."
  }
}
```

### Evaluation Result (with --show-eval)
```json
{
  "error": null,
  "score": 0.96,
  "passed": true,
  "timestamp": "2026-01-27T...",
  "evaluation": {
    "overall": {
      "score": 0.96,
      "reasoning": "Clear, correct question aligned with standard...",
      "suggested_improvements": null
    },
    "factual_accuracy": {"score": 1, "reasoning": "..."},
    "clarity_precision": {"score": 1, "reasoning": "..."},
    "distractor_quality": {"score": 0.9, "reasoning": "..."},
    ...
  }
}
```

## Grade & Standards Support

**Grades K-12:**
- K-2: Simple vocabulary, short sentences
- 3-5: Grade-level vocabulary, simple/compound sentences  
- 6-8: Academic vocabulary, complex sentences
- 9-12: Sophisticated vocabulary, advanced structures

**Standards:**
- **L.*** (Language): Grammar, vocabulary, conventions
- **RL.*** (Reading Literature): Stories, poems, drama
- **RI.*** (Reading Informational): Articles, essays
- **W.*** (Writing): Writing skills

## Key Differences: Python vs Claude Orchestration

| Aspect | Python Orchestrated | Claude Orchestrated (This Project) |
|--------|---------------------|---------------------|
| Decision making | Python code | Claude (AI) |
| Flow control | Hardcoded in pipeline.py | Claude reads SKILL.md |
| Self-correction | Not possible | Claude analyzes feedback & regenerates |
| Flexibility | Change requires code edits | Edit SKILL.md instructions |
| Adding tools | Write Python functions | Add scripts + update SKILL.md |

## Setup

### Requirements

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Install InceptBench (for evaluation)
pip install inceptbench
```

### Environment Variables

Create `.env` file:
```env
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

## Quick Start

```bash
# 1. Generate 5 questions with self-correction
python scripts/generate_and_refine.py --limit 5

# 2. View results
cat outputs/refined_generated.json
```

## Cloud Deployment

This project can be deployed as a cloud endpoint.

### Deploy to Google Cloud Run

See [DEPLOY.md](DEPLOY.md) for detailed instructions.

**Quick Deploy:**
```bash
# Build
gcloud builds submit . \
  --config cloudbuild.yaml \
  --substitutions=_IMAGE_NAME="us-central1-docker.pkg.dev/PROJECT/REPO/IMAGE:latest"

# Deploy
gcloud run deploy SERVICE_NAME \
  --image IMAGE_URL \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest
```

### API Endpoint

**POST /generate**
- Accepts InceptBench Generator API Interface format
- Returns JSON with generated questions
- Supports MCQ, MSQ, Fill-in types

## References

- [Anthropic API Documentation](https://docs.anthropic.com/)
- [InceptBench Evaluation](https://github.com/inceptbench/inceptbench)
