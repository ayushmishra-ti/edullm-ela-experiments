#!/usr/bin/env python3
"""
Evaluate generated questions using InceptBench (parallel execution).

Usage:
  python scripts/evaluate_batch.py [--input PATH] [--output-dir PATH] [--concurrency N] [--show-eval] [--debug]

Example:
  python scripts/evaluate_batch.py --concurrency 20
  python scripts/evaluate_batch.py -i outputs/cloud_endpoint_samples.json
  python scripts/evaluate_batch.py --show-eval  # Show full evaluation JSON for each item
  python scripts/evaluate_batch.py --debug      # Show inceptbench logs
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def to_inceptbench_format(item: dict) -> dict:
    """Convert item to InceptBench format."""
    request = item.get("request", {})
    content = item.get("content", {})
    
    return {
        "id": item.get("id", ""),
        "content": json.dumps(content) if isinstance(content, dict) else str(content),
        "request": {
            "grade": request.get("grade", "3"),
            "subject": request.get("subject", "ela"),
            "type": request.get("type", "mcq"),
            "difficulty": request.get("difficulty", "easy"),
            "skills": request.get("skills", {}),
        },
    }


async def evaluate_item_async(item: dict, debug: bool = False) -> dict | None:
    """Evaluate one item with InceptBench CLI (async)."""
    incept_item = to_inceptbench_format(item)
    payload = {"generated_content": [incept_item]}
    
    with tempfile.TemporaryDirectory(prefix="incept_") as td:
        in_path = Path(td) / "in.json"
        out_path = Path(td) / "out.json"
        in_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        
        # Don't pass --verbose to suppress INFO logs by default
        cmd = [sys.executable, "-m", "inceptbench", "evaluate", str(in_path), "-o", str(out_path)]
        if debug:
            cmd.append("--verbose")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                # Only print output in debug mode
                if debug and stdout:
                    print(stdout.decode("utf-8", errors="ignore"))
                if debug and stderr:
                    print(stderr.decode("utf-8", errors="ignore"))
            except asyncio.TimeoutError:
                proc.kill()
                return None
            
            if proc.returncode != 0:
                if debug and stderr:
                    print(f"    Error: {stderr.decode('utf-8', errors='ignore')}")
                return None
        except Exception as e:
            if debug:
                print(f"    Exception: {e}")
            return None
        
        if not out_path.exists():
            return None
        
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        
        # Extract evaluation
        ev = data.get("evaluations", {})
        if isinstance(ev, dict) and item.get("id") in ev:
            return ev[item.get("id")]
        
        results = data.get("results", [])
        if results and isinstance(results[0], dict):
            return results[0]
        
        if "overall" in data:
            return data
        
        return None


async def evaluate_with_semaphore(
    item: dict,
    index: int,
    total: int,
    semaphore: asyncio.Semaphore,
    show_eval: bool = False,
    debug: bool = False,
) -> tuple[int, dict, dict | None]:
    """Evaluate one item with semaphore-controlled concurrency."""
    async with semaphore:
        item_id = item.get("id", "")
        print(f"  [{index+1}/{total}] {item_id}...", end=" ", flush=True)
        
        ev = await evaluate_item_async(item, debug)
        
        if ev is None:
            print("FAIL")
        else:
            overall = ev.get("overall") or {}
            score_100 = overall.get("score_100")
            if score_100 is None:
                score = overall.get("score")
                score_100 = round(score * 100, 2) if score is not None else None
            
            if score_100 is not None:
                status = "OK" if score_100 >= 85 else "WARN"
                print(f"{status} {score_100}%")
            else:
                print("WARN No score")
            
            # Show full evaluation JSON if requested
            if show_eval and ev:
                eval_output = {
                    "error": None,
                    "score": overall.get("score"),
                    "passed": score_100 >= 85 if score_100 else False,
                    "timestamp": datetime.now().isoformat(),
                    "evaluation": ev,
                }
                print(json.dumps(eval_output, indent=2))
        
        return (index, item, ev)


async def run_evaluation(
    items: list[dict],
    concurrency: int,
    show_eval: bool = False,
    debug: bool = False,
) -> list[tuple[int, dict, dict | None]]:
    """Run all evaluations in parallel with concurrency limit."""
    semaphore = asyncio.Semaphore(concurrency)
    
    tasks = [
        evaluate_with_semaphore(item, i, len(items), semaphore, show_eval, debug)
        for i, item in enumerate(items)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out exceptions
    valid_results = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  FAIL Task failed with exception: {r}")
        else:
            valid_results.append(r)
    
    return valid_results


def main():
    parser = argparse.ArgumentParser(description="Evaluate generated questions (parallel)")
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=ROOT / "outputs" / "batch_generated.json",
        help="Input JSON file containing {'generated_content': [...]} (default: outputs/batch_generated.json)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=ROOT / "outputs",
        help="Output directory for results (writes eval_results.csv and eval_results_summary.json)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=10,
        help="Number of parallel evaluations (default: 10)",
    )
    parser.add_argument(
        "--show-eval", "-e",
        action="store_true",
        help="Show full evaluation JSON for each item",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show inceptbench INFO logs (verbose mode)",
    )
    args = parser.parse_args()

    # Common footgun: passing a file path to --output-dir (e.g. "-o outputs/some.json").
    # If it looks like a file path, treat its parent as the output directory.
    if args.output_dir.suffix:
        print(
            f"Warning: --output-dir expects a directory, but got a file path: {args.output_dir}\n"
            f"         Using parent directory instead: {args.output_dir.parent}",
            file=sys.stderr,
        )
        args.output_dir = args.output_dir.parent
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading from: {args.input}")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    
    items = data.get("generated_content", [])
    if not items:
        print("Error: No generated content found", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(items)} items to evaluate")
    print(f"Concurrency: {args.concurrency} parallel evaluations")
    print()
    
    # Run parallel evaluation
    results = asyncio.run(run_evaluation(items, args.concurrency, args.show_eval, args.debug))
    
    # Process results and build CSV rows
    csv_rows = []
    scores = []
    
    for index, item, ev in sorted(results, key=lambda x: x[0]):
        item_id = item.get("id", "")
        
        # Extract metadata from request
        request = item.get("request", {})
        substandard_id = (request.get("skills") or {}).get("substandard_id", "")
        difficulty = request.get("difficulty", "")
        question = (item.get("content") or {}).get("question", "") or ""
        question_short = (question[:120] + "…") if len(question) > 120 else question
        
        if ev is None:
            csv_rows.append({
                "id": item_id,
                "substandard_id": substandard_id,
                "difficulty": difficulty,
                "question": question_short,
                "gen_error": "",
                "overall_score": "",
                "overall_score_100": "",
                "rating": "",
                "eval_error": "inceptbench_failed",
            })
        else:
            overall = ev.get("overall", {})
            score = overall.get("score")
            score_100 = overall.get("score_100") or (round(score * 100, 2) if score is not None else None)
            rating = overall.get("rating") or ""
            
            if score_100 is not None:
                scores.append(float(score_100))
            
            csv_rows.append({
                "id": item_id,
                "substandard_id": substandard_id,
                "difficulty": difficulty,
                "question": question_short,
                "gen_error": "",
                "overall_score": score if score is not None else "",
                "overall_score_100": score_100 if score_100 is not None else "",
                "rating": rating,
                "eval_error": "",
            })
    
    # Save results
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = args.output_dir / "eval_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, 
            fieldnames=["id", "substandard_id", "difficulty", "question", "gen_error", 
                       "overall_score", "overall_score_100", "rating", "eval_error"],
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    
    # Summary
    n_total = len(items)
    n_evaluated = len(scores)
    aggregate = round(sum(scores) / n_evaluated, 2) if n_evaluated else None
    pass_count = sum(1 for s in scores if s > 85)
    pass_rate = round(100.0 * pass_count / n_evaluated, 1) if n_evaluated else None
    n_failed_eval = sum(1 for r in csv_rows if r.get("eval_error") == "inceptbench_failed")
    
    summary = {
        "n_total": n_total,
        "n_evaluated": n_evaluated,
        "aggregate_score": aggregate,
        "pass_rate_percent": pass_rate,
        "n_failed_evaluation": n_failed_eval,
        "timestamp": datetime.now().isoformat(),
    }
    
    summary_path = args.output_dir / "eval_results_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    
    print(f"\n{'='*60}")
    print("Evaluation Complete")
    print(f"{'='*60}")
    print(f"Total items: {n_total}")
    print(f"Successfully evaluated: {n_evaluated}")
    print(f"Evaluation failures: {n_failed_eval}")
    print(f"Aggregate score: {aggregate}%")
    print(f"Pass rate (>85%): {pass_rate}%")
    print(f"\nFiles saved:")
    print(f"  - {csv_path}")
    print(f"  - {summary_path}")


if __name__ == "__main__":
    main()
