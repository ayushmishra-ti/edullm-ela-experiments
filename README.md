# ccapi — Grade 3 ELA MCQ Generation with Claude Code Skills

Generate Grade 3 ELA multiple-choice questions from Common Core standards using **Claude Code Skills** as the generation engine and **[InceptBench](https://pypi.org/project/inceptbench/)** for evaluation.

## Objectives

- **Coverage**: All 465 MCQ entries in `grade-3-ela-benchmark.jsonl`
- **Quality**: Aggregate score ≥ 93, pass rate ≥ 85% (InceptBench)
- **Method**: Claude Code Skills (Anthropic Skills API or skill-as-system-prompt fallback)

## Project layout

```
ccapi/
├── skills/
│   ├── ela-mcq-generation/   # Generation skill (SKILL.md)
│   └── evaluation-criteria/  # Evaluation spec (SKILL.md)
├── src/ccapi/
│   ├── pipeline.py                    # generate_one (Skills API or fallback)
│   ├── pipeline_with_curriculum.py    # generate_one_with_curriculum (Python-orchestrated with curriculum context)
│   ├── curriculum_lookup.py           # Lookup curriculum data from curriculum.md
│   ├── populate_curriculum.py         # Generate and populate missing curriculum data
│   ├── evaluate.py                    # InceptBench via REST
│   ├── formatters.py                  # benchmark→request, normalize, InceptBench shape
│   └── config.py                      # env and paths
├── scripts/
│   ├── generate_batch.py              # Batch run over benchmark (use --use-curriculum for curriculum context)
│   ├── run_generate_evaluate_csv.py   # Generate → inceptbench CLI → CSV + aggregate
│   └── upload_skill.py                # Upload generation skill to Anthropic
├── option_c_agent_sdk/                # Fully agentic approach (Claude decides tool usage)
├── data/                     # Optional local data
├── outputs/                  # Batch and run outputs
├── ayush/                    # Python venv
├── requirements.txt
└── env.example               # Copy to .env
```

## Setup

### 1. Python environment `ayush`

```powershell
cd c:\Users\user\Documents\ccapi
.\ayush\Scripts\activate   # or: & .\ayush\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Environment

Copy `env.example` to `.env` and set:

- `ANTHROPIC_API_KEY` — required for generation
- `CCAPI_ELA_MCQ_SKILL_ID` — optional; set after `upload_skill.py` to use Skills API
- `INCEPT_API_KEY` — optional; for `--evaluate` in batch
- `CCAPI_BENCHMARK_PATH` — optional; default: `../edullm-ela-experiment/grade-3-ela-benchmark.jsonl`

### 3. Skills API (optional)

To use the **Skills API** (container + `skill_id` per [Skills guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)):

```bash
python scripts/upload_skill.py
```

`upload_skill` reads the skill from **`skills/ela-mcq-generation/SKILL.md`**, uploads it via `client.beta.skills.create`, and prints a `skill_id`. Add that as `CCAPI_ELA_MCQ_SKILL_ID` in `.env`.

If `CCAPI_ELA_MCQ_SKILL_ID` is unset, the pipeline uses the **fallback**: the same `SKILL.md` is loaded from disk and used as the system prompt in a normal `messages.create` (no container, no code_execution). See **`SKILLS_FLOW.md`** for the full flow.

### 4. Benchmark

Use `grade-3-ela-benchmark.jsonl` from the [InceptBench](https://www.inceptbench.com) site or from `edullm-ela-experiment`. Default path: `../edullm-ela-experiment/grade-3-ela-benchmark.jsonl`. Override with `--benchmark` or `CCAPI_BENCHMARK_PATH`.

## Usage

### Generate one (programmatic)

```python
import asyncio
from ccapi.pipeline import generate_one

async def main():
    req = {
        "type": "mcq",
        "grade": "3",
        "skills": {
            "lesson_title": "",
            "substandard_id": "CCSS.ELA-LITERACY.L.3.1.E",
            "substandard_description": "Form and use the simple verb tenses."
        },
        "subject": "ela",
        "curriculum": "common core",
        "difficulty": "easy"
    }
    res = await generate_one(req)
    # res["generatedContent"]["generated_content"][0]

asyncio.run(main())
```

### Generate with curriculum context

Use the curriculum-aware pipeline for better alignment with assessment boundaries and common misconceptions:

```python
import asyncio
from ccapi.pipeline_with_curriculum import generate_one_with_curriculum

async def main():
    req = {
        "type": "mcq",
        "grade": "3",
        "skills": {
            "substandard_id": "CCSS.ELA-LITERACY.L.3.1.E",
            "substandard_description": "Form and use the simple verb tenses."
        },
        "subject": "ela",
        "curriculum": "common core",
        "difficulty": "easy"
    }
    # Python orchestrates: looks up curriculum, populates if missing, uses in prompt
    res = await generate_one_with_curriculum(req)

asyncio.run(main())
```

Or use the batch script with `--use-curriculum` flag (see below).

### Batch generate

```bash
# All MCQs (465), no evaluation
python scripts/generate_batch.py

# Limit 5, with InceptBench evaluation
python scripts/generate_batch.py --limit 5 --evaluate

# With curriculum context (looks up and populates curriculum.md data)
python scripts/generate_batch.py --limit 5 --use-curriculum

# Custom paths
python scripts/generate_batch.py --benchmark path/to/grade-3-ela-benchmark.jsonl -o outputs/run1.json
```

### Generate → inceptbench CLI → CSV + aggregate (no REST API)

Runs the generator on benchmark rows, evaluates each with the **inceptbench CLI** (no `httpx` POST to api.inceptbench.com), writes a **CSV** and a **summary** with aggregate score and pass rate:

```bash
pip install inceptbench   # requires Python 3.11-3.13
python scripts/run_generate_evaluate_csv.py --benchmark grade-3-ela-benchmark.jsonl --limit 5 -o outputs/eval_results.csv
```

- **CSV**: `id`, `substandard_id`, `difficulty`, `question`, `gen_error`, `overall_score`, `overall_score_100`, `rating`, `eval_error`
- **Summary** `outputs/eval_results_summary.json`: `n_total`, `n_evaluated`, `aggregate_score` (mean of `overall_score_100`), `pass_rate_percent` (% with score > 85)

### InceptBench (evaluation)

- **REST**: `evaluate.py` calls `https://api.inceptbench.com/evaluate` with `Authorization: Bearer INCEPT_API_KEY`.
- **inceptbench package** (optional): `pip install inceptbench` (requires Python 3.11–3.13). CLI: `inceptbench evaluate content.json -o results.json`. `run_generate_evaluate_csv.py` uses the CLI only (no REST, no API key).

The **evaluation skill** (`skills/evaluation-criteria/SKILL.md`) defines targets and InceptBench format; the actual API call runs in Python (Skills run in a sandbox with no network).

## Skills

| Skill | Role |
|-------|------|
| `ela-mcq-generation` | Generation: input/output schema, difficulty, distractors, ID rules, examples. |
| `evaluation-criteria` | Evaluation: InceptBench in/out, score 0–100, targets (aggregate ≥93, pass ≥85%), accept/revise/reject. |

## Output

- **Single**: `{ "error", "success", "timestamp", "generatedContent": { "generated_content": [ { "id", "content", "request" } ] } }`
- **Batch**: `{ "benchmark", "limit", "total_requested", "total_generated", "generation_mode", "errors", "generated_content": [ ... ] }`  
  - `generation_mode`: `"skills_api"` (container + custom skill) or `"fallback"` (skill from file as system prompt) or `"unknown"`.

## ccapi vs option_c_agent_sdk

The main difference between `ccapi` and `option_c_agent_sdk` lies in their orchestration approach: `ccapi` uses a **Python-orchestrated workflow** where your Python code explicitly controls when to lookup curriculum data, populate missing entries, and inject context into prompts before calling Claude via the Skills API (or fallback mode), while `option_c_agent_sdk` uses a **fully agentic approach** with the Claude Agent SDK where Claude autonomously decides when to call tools like curriculum lookup and population, giving Claude complete control over the workflow rather than having Python pre-fetch and inject curriculum context. Both approaches support curriculum-aware generation, but `ccapi` relies on Python to orchestrate the steps (lookup → populate → inject → generate), whereas `option_c_agent_sdk` provides Claude with custom MCP tools and lets it decide when and how to use them during generation.

## References

- **`PROJECT_DECISIONS_AND_RUNBOOK.md`** — decisions in plain English and steps to run (no implementation code)
- [Claude Skills guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- **`SKILLS_FLOW.md`** — custom skill, container, and where `upload_skill` gets the skill
- [InceptBench (PyPI)](https://pypi.org/project/inceptbench/)
- Pre-experiment plan: `SECTION 1–4` in the project brief (objectives, architecture, risks, decision framework).
