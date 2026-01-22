#!/usr/bin/env python3
"""
Batch generate Grade 3 ELA MCQs from benchmark and optionally evaluate with InceptBench.

Usage:
  From project root (ccapi):
    python scripts/generate_batch.py [--benchmark PATH] [--output PATH] [--limit N] [--evaluate|--evaluation] [--use-curriculum]

  Env: ANTHROPIC_API_KEY (required), 
       CCAPI_ELA_MCQ_SKILL_ID (optional), CCAPI_POPULATE_CURRICULUM_SKILL_ID (optional).
  Benchmark: grade-3-ela-benchmark.jsonl; default from CCAPI_BENCHMARK_PATH or
  ../edullm-ela-experiment/grade-3-ela-benchmark.jsonl.
  
  --use-curriculum: Use curriculum context (looks up and populates curriculum.md data)
  --evaluate/--evaluation: Run InceptBench evaluation per item (no API key required)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# Project root and src
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from ccapi.config import CCAPI_BENCHMARK_PATH
from ccapi.formatters import benchmark_row_to_request
from ccapi.pipeline import generate_one
from ccapi.pipeline_with_curriculum import generate_one_with_curriculum
# evaluate_item imported lazily only when --evaluate is used


def _default_benchmark() -> Path:
    if CCAPI_BENCHMARK_PATH and CCAPI_BENCHMARK_PATH.exists():
        return CCAPI_BENCHMARK_PATH
    return ROOT.parent / "edullm-ela-experiment" / "grade-3-ela-benchmark.jsonl"


def load_mcq_requests(benchmark_path: Path, limit: int | None) -> list[dict]:
    out = []
    with open(benchmark_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("type") != "mcq":
                continue
            out.append(benchmark_row_to_request(d))
            if limit is not None and len(out) >= limit:
                break
    return out


async def run(
    benchmark_path: Path,
    output_path: Path,
    limit: int | None,
    do_evaluate: bool,
    use_curriculum: bool,
) -> None:
    requests = load_mcq_requests(benchmark_path, limit)
    if not requests:
        print("No MCQ rows in benchmark.", file=sys.stderr)
        sys.exit(1)
    print(f"Generating {len(requests)} MCQs from {benchmark_path}")

    all_items = []
    errors = []
    generation_mode = None
    # Lazy import: only load evaluate_item when --evaluate is used
    evaluate_item = None
    if do_evaluate:
        try:
            from ccapi.evaluate import evaluate_item as _eval_item
            evaluate_item = _eval_item
            print("Evaluation: Enabled (using InceptBench package)")
        except ImportError:
            print("Warning: inceptbench package not installed. Install with: pip install inceptbench")
            print("         Evaluation will be skipped.")
            do_evaluate = False

    # Prepare CSV if evaluation is enabled
    csv_path = None
    csv_writer = None
    csv_file = None
    csv_rows = []
    scores_100 = []
    
    if do_evaluate:
        csv_path = output_path.parent / "eval_results.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = open(csv_path, "w", newline="", encoding="utf-8")
        csv_writer = csv.DictWriter(
            csv_file,
            fieldnames=["id", "substandard_id", "difficulty", "question", "gen_error", 
                       "overall_score", "overall_score_100", "rating", "eval_error"],
            extrasaction="ignore"
        )
        csv_writer.writeheader()

    for i, req in enumerate(requests):
        sid = req.get("skills", {}).get("substandard_id", "?")
        diff = req.get("difficulty", "?")
        print(f"  [{i+1}/{len(requests)}] {sid} ({diff})")
        if use_curriculum:
            res = await generate_one_with_curriculum(req)
        else:
            res = await generate_one(req)
        if generation_mode is None:
            generation_mode = res.get("generation_mode")
        if not res.get("success"):
            errors.append({"request": req, "error": res.get("error", "unknown")})
            if do_evaluate and csv_writer:
                row = {
                    "id": "",
                    "substandard_id": sid,
                    "difficulty": diff,
                    "question": "",
                    "gen_error": res.get("error", "unknown"),
                    "overall_score": "",
                    "overall_score_100": "",
                    "rating": "",
                    "eval_error": "not_evaluated",
                }
                csv_writer.writerow(row)
                csv_rows.append(row)
            continue
        items = res.get("generatedContent", {}).get("generated_content", [])
        if not items:
            if do_evaluate and csv_writer:
                row = {
                    "id": "",
                    "substandard_id": sid,
                    "difficulty": diff,
                    "question": "",
                    "gen_error": "no_item",
                    "overall_score": "",
                    "overall_score_100": "",
                    "rating": "",
                    "eval_error": "not_evaluated",
                }
                csv_writer.writerow(row)
                csv_rows.append(row)
            continue
        
        for it in items:
            # Keep items in original format (id, content, request) - NO evaluation field
            # Items should match InceptBench input format structure
            all_items.append(it)
            
            # If evaluation is enabled, evaluate and write to CSV (but don't modify item)
            if evaluate_item is not None:
                item_id = it.get("id", "")
                q = (it.get("content") or {}).get("question", "") or ""
                q_short = (q[:120] + "…") if len(q) > 120 else q
                
                ev = await evaluate_item(it)
                
                if csv_writer:
                    if ev is None:
                        row = {
                            "id": item_id,
                            "substandard_id": sid,
                            "difficulty": diff,
                            "question": q_short,
                            "gen_error": "",
                            "overall_score": "",
                            "overall_score_100": "",
                            "rating": "",
                            "eval_error": "inceptbench_failed",
                        }
                    else:
                        overall = ev.get("overall") or {}
                        overall_score = overall.get("score")
                        overall_score_100 = overall.get("score_100")
                        rating = overall.get("rating") or ""
                        
                        if overall_score_100 is not None:
                            scores_100.append(float(overall_score_100))
                        
                        row = {
                            "id": item_id,
                            "substandard_id": sid,
                            "difficulty": diff,
                            "question": q_short,
                            "gen_error": "",
                            "overall_score": overall_score if overall_score is not None else "",
                            "overall_score_100": overall_score_100 if overall_score_100 is not None else "",
                            "rating": rating,
                            "eval_error": "",
                        }
                    csv_writer.writerow(row)
                    csv_rows.append(row)

    # Close CSV file if opened
    if csv_file:
        csv_file.close()

    payload = {
        "benchmark": str(benchmark_path),
        "limit": limit,
        "total_requested": len(requests),
        "total_generated": len(all_items),
        "generation_mode": generation_mode or "unknown",
        "errors": errors,
        "generated_content": all_items,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {output_path} ({len(all_items)} items, {len(errors)} errors)")

    # Write evaluation summary if evaluation was enabled
    if do_evaluate and csv_path:
        n_total = len(csv_rows)
        n_evaluated = len(scores_100)
        aggregate_score = round(sum(scores_100) / n_evaluated, 2) if n_evaluated else None
        pass_count = sum(1 for s in scores_100 if s > 85)
        pass_rate = round(100.0 * pass_count / n_evaluated, 1) if n_evaluated else None
        n_failed_gen = sum(1 for r in csv_rows if r.get("gen_error"))
        n_failed_eval = sum(1 for r in csv_rows if r.get("eval_error") == "inceptbench_failed")

        summary = {
            "n_total": n_total,
            "n_evaluated": n_evaluated,
            "aggregate_score": aggregate_score,
            "pass_rate_percent": pass_rate,
            "n_failed_generation": n_failed_gen,
            "n_failed_evaluation": n_failed_eval,
            "generation_mode": generation_mode or "unknown",
            "timestamp": datetime.now().isoformat(),
        }
        
        summary_path = output_path.parent / "eval_results_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote {csv_path} ({n_evaluated} evaluated)")
        print(f"Wrote {summary_path}")
        print(f"  Aggregate score: {aggregate_score}%")
        print(f"  Pass rate (>85%): {pass_rate}%")


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch generate Grade 3 ELA MCQs.")
    ap.add_argument("--benchmark", type=Path, default=None, help="Benchmark JSONL path")
    ap.add_argument("--output", "-o", type=Path, default=None, help="Output JSON path")
    ap.add_argument("--limit", type=int, default=None, help="Max number of MCQs")
    ap.add_argument("--evaluate", action="store_true", help="Run InceptBench evaluation per item")
    ap.add_argument("--evaluation", action="store_true", help="Alias for --evaluate (Run InceptBench evaluation per item)")
    ap.add_argument("--use-curriculum", action="store_true", help="Use curriculum context (lookup and populate curriculum data)")
    args = ap.parse_args()
    
    # --evaluation is alias for --evaluate
    do_evaluate = args.evaluate or args.evaluation

    bench = args.benchmark or _default_benchmark()
    if not bench.exists():
        print(f"Benchmark not found: {bench}", file=sys.stderr)
        sys.exit(1)

    out = args.output
    if out is None:
        out = ROOT / "outputs" / "batch_generated.json"

    asyncio.run(run(bench, out, args.limit, do_evaluate, args.use_curriculum))


if __name__ == "__main__":
    main()
