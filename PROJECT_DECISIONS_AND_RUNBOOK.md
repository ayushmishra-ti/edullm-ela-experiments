# ccapi: Project Decisions and Runbook

A plain-English record of the decisions made in this project and the steps to run it. No implementation code; only narrative and the commands you need to type.

---

## 1. Project Overview

**What it does:** Generates Grade 3 English Language Arts (ELA) multiple-choice questions from Common Core standards, then evaluates them with InceptBench and writes the results to a CSV plus an aggregate summary.

**Scope:** Only MCQ (multiple-choice) rows from the Grade 3 ELA benchmark. The benchmark also has fill-in and MSQ; those are ignored.

**Goals (from the pre-experiment plan):** Generate all 465 MCQ benchmark rows; reach an aggregate InceptBench score of at least 93 and a pass rate of at least 85% (pass = score above 85). The scripts support running on a subset first (e.g. with a limit).

---

## 2. Generation: How Questions Are Produced

### Single source of truth: the generation skill

All generation behaviour (what to produce, shape of the output, difficulty rules, distractor rules, how to form IDs) lives in one place: the file **`skills/ela-mcq-generation/SKILL.md`**. There are no separate YAML prompts or other instruction files for generation. The skill is the specification.

### Two ways to run the generator: Skills API vs fallback

The project supports two modes. The choice is made automatically from configuration; you do not switch it in scripts.

- **Skills API (container) mode:** The skill is uploaded to Anthropic once. Each generation request calls the Messages API with a *container* that points to that skill and uses the *code execution* tool. This matches the official Claude Skills flow: custom skill plus container.

- **Fallback mode:** The same `SKILL.md` file is read from disk and pasted into the *system* prompt of a normal Messages API call. No upload, no container, no code execution. Behaviour is similar, but it is not the official Skills + container path.

**Decision:** Support both. If the environment variable for the uploaded skill ID is set, use Skills API mode. If not, use fallback so the project still runs without any upload step. The batch output records which mode was used so you can tell later.

### Where the skill comes from for upload

The upload script uses only the file **`skills/ela-mcq-generation/SKILL.md`**. The folder name must match the skill name declared inside that file; that is a requirement of the Skills API.

### What goes into the model as input

Each benchmark row is turned into a *request* object: grade, subject, type (mcq), curriculum (common core), difficulty, and a *skills* block with substandard ID and description. Lesson title is left empty because the benchmark does not provide it. That request is sent to the model as the user message (as JSON). The skill defines how to interpret it and what to return.

### Output shape and strict rules

The skill specifies that the model must return only a single JSON object: an ID, and a *content* block with question text, exactly four options (A–D), one correct answer, an explanation, and an image-URL list that must always be empty (no images). The pipeline then normalises the answer options into a fixed list shape and forces the image list to empty, so the rest of the system always sees a consistent structure.

---

## 3. Skills: What Exists and What They Do

### Generation skill (`ela-mcq-generation`)

One skill is used for generation. It defines input and output format, difficulty (easy / medium / hard), distractor rules, ID rules, and worked examples. It also states that the response must be **only** that JSON, with no markdown or extra text. The pipeline relies on this to parse the reply.

### Evaluation-criteria skill (`evaluation-criteria`)

A second skill describes how evaluation works: what InceptBench expects, how scores are scaled to 0–100, and what the quality targets are (aggregate and pass rate). It does **not** perform evaluation. Evaluation runs in Python (see below). This skill is a written specification for humans and for possible later tooling; it is not executed in a container.

---

## 4. Evaluation: InceptBench

### Prefer the InceptBench CLI over calling the REST API

The project avoids depending on the InceptBench REST API (and an API key) for the main evaluate-then-CSV workflow. Instead, evaluation is done by running the **inceptbench** CLI (from the PyPI package): one temporary input file per item, run the evaluate command, read the output file. No HTTP calls to api.inceptbench.com from our code in that path.

**Decision:** Use the inceptbench CLI so you can run the full generate–evaluate–CSV flow without obtaining or configuring an InceptBench API key. The REST-based path remains available in the codebase for batch generate with the `--evaluate` flag, but the CSV/aggregate runbook does not rely on it.

### InceptBench input must match their expected format

InceptBench expects a JSON object with a **`generated_content`** array. Each element must have: **id**, **curriculum** (e.g. common_core), **request** (grade, subject, type, difficulty, locale, skills, instruction), and **content**. Their examples show **content** as a **single string** in the form: question text, then a space, then the options as `A) … B) … C) … D) …`.

**Decision:** When building the payload for the inceptbench CLI, we convert our structured content (question, answer, answer_options, etc.) into that one string: the question followed by each option as `key) text`. The request block is filled from our generation request, with locale and instruction defaulted when missing. This keeps the payload compatible with InceptBench’s documented format.

### Evaluation can fail without failing the whole run

If the inceptbench CLI is missing, errors, or returns something we cannot parse, we do not abort the whole batch. For that item we still write a CSV row: we leave the score and rating blank and put a short note in an *eval error* column. The run continues, and the aggregate is computed only over items that did produce a numeric score.

---

## 5. Benchmark and Data Flow

### Benchmark file and which rows are used

The benchmark is a JSONL file (one JSON object per line). We only consider lines where the **type** field is **mcq**. Each such line is converted into the request shape described above. You can limit how many of these rows are processed (e.g. for quick tests).

**Default path:** The scripts look for the benchmark next to the `edullm-ela-experiment` folder, or you can set an environment variable or pass a path on the command line.

### From benchmark row to CSV row

For each selected MCQ row we: (1) build the request, (2) call the generator, (3) on success, convert the generated item to the InceptBench string format and run the inceptbench CLI, (4) parse the CLI output for score and rating, and (5) write one CSV row. If generation fails, we still write a row, with the generation error in its own column and no evaluation. If only evaluation fails, the row has the question and metadata, with an evaluation error note.

---

## 6. CSV and Summary Outputs

### CSV columns

Each run that produces a CSV uses a fixed set of columns: **id**, **substandard_id**, **difficulty**, **question** (truncated if very long), **gen_error**, **overall_score** (0–1), **overall_score_100** (0–100), **rating**, and **eval_error**. Empty or not-applicable values are left blank so the file stays easy to open in a spreadsheet.

### Summary file and aggregate metrics

In addition to the CSV, a **summary** file is written next to it (same base name with a `_summary` suffix and a `.json` extension). It contains:

- **n_total:** number of benchmark rows processed.
- **n_evaluated:** number of rows that got a numeric InceptBench score.
- **aggregate_score:** mean of the 0–100 scores over the evaluated rows. If none were evaluated, this is null.
- **pass_rate_percent:** percentage of evaluated rows with score greater than 85. Again, null if there is nothing to evaluate.

**Decision:** Aggregates are computed only over successfully evaluated items. Rows that failed generation or evaluation are still in the CSV for inspection but do not affect the aggregate or pass rate.

---

## 7. Errors and Robustness

### Generation failures

If the model returns invalid JSON, empty text, or something that does not match the expected shape, we treat it as a generation failure. We write a CSV row with the request metadata and a short error description. We do not call InceptBench for that row.

### Inceptbench not installed or not runnable

Before running the generate–evaluate–CSV script, we check that the inceptbench CLI is available (by running its version or help command). If it is not, we print a clear message and exit. We do not generate and then fail on the first evaluate.

### Inceptbench CLI or parse failures per item

If, for a given item, the CLI fails or the output cannot be parsed for a score, we still write the CSV row, leave score and rating blank, and set the eval error note. The run continues.

---

## 8. Configuration and Environment

### What you must set

- **ANTHROPIC_API_KEY:** Needed for all generation. Without it, generation does not run.

### What is optional

- **CCAPI_ELA_MCQ_SKILL_ID:** If set, the pipeline uses the Skills API (container) mode. If unset, it uses the fallback (skill from disk in the system prompt).
- **INCEPT_API_KEY:** Only used by the batch generator’s REST-based evaluation path when you pass the evaluate flag. The CSV/aggregate workflow does not use it.
- **CCAPI_BENCHMARK_PATH:** Overrides the default path to the benchmark file. You can also pass the path on the command line.

Configuration is read from a `.env` file in the project root when available.

---

## 9. Steps to Run

### Prerequisites

- Python 3.11, 3.12, or 3.13 (needed for the inceptbench package; the rest of the project may run on 3.14, but the CSV evaluation path requires inceptbench).
- A copy of **grade-3-ela-benchmark.jsonl** (from the InceptBench site or the edullm-ela-experiment repo).
- An Anthropic API key.

---

### Step 1: Create and activate the Python environment

Go to the project folder and create a virtual environment named **ayush** (or reuse it if it already exists). Activate it. On Windows, activation is typically by running the `Activate` script in the `Scripts` folder of the environment.

---

### Step 2: Install dependencies

Install the project’s main dependencies (e.g. from `requirements.txt`). Then install the **inceptbench** package so its CLI is available. If your Python is 3.14, inceptbench may not install; use 3.11–3.13 for the CSV evaluation flow.

---

### Step 3: Configure environment variables

Copy the example env file to a file named `.env` in the project root. Set **ANTHROPIC_API_KEY** to your key. Leave the skill ID and InceptBench key unset unless you plan to use those features.

---

### Step 4 (optional): Upload the generation skill for Skills API mode

If you want to use the official Skills API (container) path instead of the fallback, run the upload script once. It reads the skill from `skills/ela-mcq-generation/SKILL.md`, uploads it to Anthropic, and prints a skill ID. Put that value into `.env` as **CCAPI_ELA_MCQ_SKILL_ID**. If you skip this, the pipeline will use the fallback and still generate.

---

### Step 5: Run the generator + InceptBench + CSV pipeline

Run the script that: loads MCQ rows from the benchmark, generates one question per row, evaluates each with the inceptbench CLI, writes a CSV, and writes the summary file.

You can pass:

- The path to the benchmark file (or rely on the default / environment variable).
- A limit (e.g. 5 or 10) for an initial test, or omit it to process all MCQ rows.
- The path where the CSV should be written (or use the default under `outputs`).

**Command (example):** From the project root, with the environment activated, run the run script. Give the benchmark path, a limit, and the output CSV path. The default CSV path is `outputs/eval_results.csv`; the summary is written to `outputs/eval_results_summary.json` (or the same stem as your CSV with `_summary.json` appended).

The script checks that the inceptbench CLI is available before starting. If it is not, it exits with a short message.

---

### Step 6: Inspect outputs

- Open the CSV (e.g. in Excel or a text editor) to see, per row: id, substandard, difficulty, question snippet, any gen or eval errors, and—when evaluation succeeded—overall score (0–1 and 0–100) and rating.
- Open the summary JSON to see: how many rows were processed, how many were evaluated, the aggregate score, and the pass rate (percent of evaluated rows with score above 85).

---

### Alternative: Batch generate only (JSON, no CSV)

If you only want to generate and get a JSON file (and optionally use the REST evaluation path with an InceptBench API key), run the batch generate script instead. You can pass a benchmark path, a limit, and an output path. The output is JSON with a list of generated items and, if you used the evaluate flag and set the key, evaluation data on each. This path does not produce the CSV or the aggregate summary.

---

## 10. Commands to Run (Quick Reference)

From the project root, with the **ayush** (or your) environment activated:

**Install inceptbench (for the CSV pipeline):**  
`pip install inceptbench`

**Upload the skill (optional; for Skills API mode):**  
`python scripts/upload_skill.py`  
Then add the printed skill ID to `.env` as `CCAPI_ELA_MCQ_SKILL_ID`.

**Generate + evaluate + CSV + aggregate (main workflow):**  
`python scripts/run_generate_evaluate_csv.py --benchmark grade-3-ela-benchmark.jsonl --limit 5 -o outputs/eval_results.csv`  
Use `--limit` to test on a few rows first; omit it to run on all MCQ rows. Change `--benchmark` or `-o` as needed.

**Batch generate only (JSON, no CSV):**  
`python scripts/generate_batch.py --benchmark grade-3-ela-benchmark.jsonl --limit 5 -o outputs/batch_generated.json`  
Add `--evaluate` and set `INCEPT_API_KEY` in `.env` if you want REST-based evaluation on each item.

---

## 11. Where Things Live (Files and Folders)

- **Generation skill:** `skills/ela-mcq-generation/SKILL.md`
- **Evaluation spec (skill):** `skills/evaluation-criteria/SKILL.md`
- **Upload script:** `scripts/upload_skill.py`
- **Batch generate (JSON):** `scripts/generate_batch.py`
- **Generate + InceptBench CLI + CSV + summary:** `scripts/run_generate_evaluate_csv.py`
- **Config and env:** `.env` in the project root; `env.example` as a template.
- **Outputs:** By default, under `outputs/` (CSV, summary JSON, and any batch JSON you choose to write there).

---

## 12. References

- Claude Skills guide (custom skill, container, code execution): [platform.claude.com/docs/en/build-with-claude/skills-guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- InceptBench (CLI, input format, API): [pypi.org/project/inceptbench/](https://pypi.org/project/inceptbench/)
- In this repo: **README.md** (commands and layout), **SKILLS_FLOW.md** (Skills API vs fallback, where the skill comes from).
