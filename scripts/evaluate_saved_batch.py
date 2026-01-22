#!/usr/bin/env python3
"""
Evaluate previously generated MCQs from a saved batch_generated.json file.

This script loads a saved batch_generated.json file, evaluates each item with InceptBench
in parallel, and saves results to eval_results.csv and eval_results_summary.json.

Usage:
  From project root (ccapi):
    python scripts/evaluate_saved_batch.py [--input PATH] [--output-dir PATH] [--concurrency N]

  --input: Path to batch_generated.json file (default: outputs/batch_generated.json)
  --output-dir: Directory to save CSV and summary (default: outputs/)
  --concurrency: Number of parallel evaluations (default: 10, increase for faster evaluation)
  
  Example:
    # Evaluate with default 10 concurrent evaluations
    python scripts/evaluate_saved_batch.py
    
    # Evaluate with 20 concurrent evaluations (faster)
    python scripts/evaluate_saved_batch.py --concurrency 20
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

from ccapi.evaluate import evaluate_item


async def evaluate_item_with_progress(
    item: dict,
    index: int,
    total: int,
    semaphore: asyncio.Semaphore,
) -> tuple[int, dict, dict | None]:
    """
    Evaluate one item with semaphore-controlled concurrency.
    
    Returns:
        (index, item, evaluation_result)
    """
    async with semaphore:
        item_id = item.get("id", "")
        print(f"  [{index+1}/{total}] Evaluating {item_id}...")
        ev = await evaluate_item(item)
        
        if ev is None:
            print(f"    ✗ Evaluation failed for {item_id}")
        else:
            overall_score_100 = (ev.get("overall") or {}).get("score_100")
            if overall_score_100 is not None:
                print(f"    ✓ {item_id}: {overall_score_100}%")
            else:
                print(f"    ⚠ {item_id}: Evaluation completed but no score")
        
        return (index, item, ev)


async def evaluate_saved_batch(
    input_path: Path,
    output_dir: Path,
    concurrency: int = 10,
) -> None:
    """
    Load a saved batch_generated.json file and evaluate all items in parallel.
    
    Args:
        input_path: Path to batch_generated.json file
        output_dir: Directory to save eval_results.csv and eval_results_summary.json
        concurrency: Number of concurrent evaluations (default: 10)
    """
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading generated content from: {input_path}")
    
    # Load the saved batch file
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            batch_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON file: {e}", file=sys.stderr)
        sys.exit(1)
    
    all_items = batch_data.get("generated_content", [])
    if not all_items:
        print("Error: No generated content found in file.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(all_items)} items to evaluate")
    print(f"Evaluation: Enabled (using InceptBench CLI)")
    print(f"Concurrency: {concurrency} parallel evaluations")
    print(f"Starting parallel evaluation...\n")
    
    # Create semaphore to limit concurrent evaluations
    semaphore = asyncio.Semaphore(concurrency)
    
    # Create evaluation tasks
    tasks = [
        evaluate_item_with_progress(item, i, len(all_items), semaphore)
        for i, item in enumerate(all_items)
    ]
    
    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results in order
    evaluated_items = [None] * len(all_items)
    evaluations_by_id = {}  # Store evaluations separately by item ID
    csv_rows = []
    scores_100 = []
    
    for result in results:
        if isinstance(result, Exception):
            print(f"  ✗ Task failed with exception: {result}")
            continue
        
        index, item, ev = result
        # Keep the item in its original format (id, content, request) - no evaluation field
        evaluated_items[index] = dict(item)
        # Store evaluation separately by item ID
        item_id = item.get("id", "")
        if item_id:
            evaluations_by_id[item_id] = ev
        
        # Prepare CSV row
        request = item.get("request", {})
        sid = (request.get("skills") or {}).get("substandard_id", "")
        diff = request.get("difficulty", "")
        q = (item.get("content") or {}).get("question", "") or ""
        q_short = (q[:120] + "…") if len(q) > 120 else q
        
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
        
        csv_rows.append(row)
    
    # Write CSV
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "eval_results.csv"
    
    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        csv_writer = csv.DictWriter(
            csv_file,
            fieldnames=["id", "substandard_id", "difficulty", "question", "gen_error", 
                       "overall_score", "overall_score_100", "rating", "eval_error"],
            extrasaction="ignore"
        )
        csv_writer.writeheader()
        csv_writer.writerows(csv_rows)
    
    # Calculate summary statistics
    n_total = len(csv_rows)
    n_evaluated = len(scores_100)
    aggregate_score = round(sum(scores_100) / n_evaluated, 2) if n_evaluated else None
    pass_count = sum(1 for s in scores_100 if s > 85)
    pass_rate = round(100.0 * pass_count / n_evaluated, 1) if n_evaluated else None
    n_failed_eval = sum(1 for r in csv_rows if r.get("eval_error") == "inceptbench_failed")
    
    summary = {
        "n_total": n_total,
        "n_evaluated": n_evaluated,
        "aggregate_score": aggregate_score,
        "pass_rate_percent": pass_rate,
        "n_failed_evaluation": n_failed_eval,
        "generation_mode": batch_data.get("generation_mode", "unknown"),
        "timestamp": datetime.now().isoformat(),
    }
    
    summary_path = output_dir / "eval_results_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    
    # Update the original batch file - keep items in original format (no evaluation field)
    batch_data["generated_content"] = evaluated_items
    # Optionally store evaluations in a separate field if needed
    if evaluations_by_id:
        batch_data["evaluations"] = evaluations_by_id
    input_path.write_text(json.dumps(batch_data, indent=2), encoding="utf-8")
    
    print("\n" + "=" * 60)
    print("Evaluation Complete")
    print("=" * 60)
    print(f"Total items: {n_total}")
    print(f"Successfully evaluated: {n_evaluated}")
    print(f"Evaluation failures: {n_failed_eval}")
    print(f"Aggregate score: {aggregate_score}%")
    print(f"Pass rate (>85%): {pass_rate}%")
    print(f"\nFiles saved:")
    print(f"  - {csv_path}")
    print(f"  - {summary_path}")
    print(f"  - {input_path} (updated with evaluations)")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Evaluate previously generated MCQs from a saved batch_generated.json file."
    )
    ap.add_argument(
        "--input", 
        type=Path, 
        default=None,
        help="Path to batch_generated.json file (default: outputs/batch_generated.json)"
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to save CSV and summary (default: outputs/)"
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent evaluations (default: 10, increase for faster evaluation)"
    )
    args = ap.parse_args()
    
    input_path = args.input or (ROOT / "outputs" / "batch_generated.json")
    output_dir = args.output_dir or (ROOT / "outputs")
    
    asyncio.run(evaluate_saved_batch(input_path, output_dir, args.concurrency))


if __name__ == "__main__":
    main()
