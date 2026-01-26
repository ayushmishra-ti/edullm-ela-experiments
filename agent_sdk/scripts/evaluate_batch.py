#!/usr/bin/env python3
"""
Evaluate generated questions using InceptBench.

Usage:
  python scripts/evaluate_batch.py [--input PATH] [--output-dir PATH] [--verbose]

Example:
  python scripts/evaluate_batch.py --verbose
"""

from __future__ import annotations

import argparse
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


def evaluate_item(item: dict, verbose: bool = False) -> dict | None:
    """Evaluate one item with InceptBench CLI."""
    incept_item = to_inceptbench_format(item)
    payload = {"generated_content": [incept_item]}
    
    with tempfile.TemporaryDirectory(prefix="incept_") as td:
        in_path = Path(td) / "in.json"
        out_path = Path(td) / "out.json"
        in_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        
        cmd = [sys.executable, "-m", "inceptbench", "evaluate", str(in_path), "-o", str(out_path)]
        if verbose:
            cmd.append("--verbose")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return None
        except Exception:
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


def main():
    parser = argparse.ArgumentParser(description="Evaluate generated questions")
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=ROOT / "outputs" / "batch_generated.json",
        help="Input batch_generated.json file",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=ROOT / "outputs",
        help="Output directory for results",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Pass --verbose to inceptbench",
    )
    args = parser.parse_args()
    
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
    if args.verbose:
        print("Verbose mode: ON (passing --verbose to inceptbench)")
    print()
    
    # Evaluate
    csv_rows = []
    scores = []
    
    for i, item in enumerate(items):
        item_id = item.get("id", "")
        print(f"  [{i+1}/{len(items)}] {item_id}...", end=" ")
        
        ev = evaluate_item(item, args.verbose)
        
        if ev is None:
            print("✗ Failed")
            csv_rows.append({
                "id": item_id,
                "score": "",
                "score_100": "",
                "error": "inceptbench_failed",
            })
        else:
            overall = ev.get("overall", {})
            score = overall.get("score")
            score_100 = round(score * 100, 2) if score is not None else None
            
            if score_100 is not None:
                scores.append(score_100)
                status = "✓" if score_100 >= 85 else "⚠ LOW"
                print(f"{status} {score_100}%")
            else:
                print("⚠ No score")
            
            csv_rows.append({
                "id": item_id,
                "score": score or "",
                "score_100": score_100 or "",
                "error": "",
            })
    
    # Save results
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = args.output_dir / "eval_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "score", "score_100", "error"])
        writer.writeheader()
        writer.writerows(csv_rows)
    
    # Summary
    n_total = len(items)
    n_evaluated = len(scores)
    aggregate = round(sum(scores) / n_evaluated, 2) if n_evaluated else None
    pass_count = sum(1 for s in scores if s > 85)
    pass_rate = round(100.0 * pass_count / n_evaluated, 1) if n_evaluated else None
    
    summary = {
        "n_total": n_total,
        "n_evaluated": n_evaluated,
        "aggregate_score": aggregate,
        "pass_rate_percent": pass_rate,
        "n_failed": n_total - n_evaluated,
        "timestamp": datetime.now().isoformat(),
    }
    
    summary_path = args.output_dir / "eval_results_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    
    print(f"\n{'='*60}")
    print("Evaluation Complete")
    print(f"{'='*60}")
    print(f"Total: {n_total}")
    print(f"Evaluated: {n_evaluated}")
    print(f"Aggregate score: {aggregate}%")
    print(f"Pass rate (>85%): {pass_rate}%")
    print(f"\nFiles saved:")
    print(f"  - {csv_path}")
    print(f"  - {summary_path}")


if __name__ == "__main__":
    main()
