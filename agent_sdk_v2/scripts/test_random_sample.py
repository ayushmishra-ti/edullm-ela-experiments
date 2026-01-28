#!/usr/bin/env python3
"""
Test the agentic pipeline on a random sample of 200 questions from all benchmarks.

Usage:
  python scripts/test_random_sample.py
  python scripts/test_random_sample.py --sample-size 50
  python scripts/test_random_sample.py --sample-size 200 --verbose
  python scripts/test_random_sample.py --dry-run  # Just show sample without running pipeline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parents[1]

# Add src to path
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass


def load_all_benchmarks(data_dir: Path) -> list[dict]:
    """Load and combine all benchmark JSONL files from data directory."""
    all_requests = []
    benchmark_files = list(data_dir.glob("grade-*-ela-benchmark.jsonl"))
    
    print(f"Found {len(benchmark_files)} benchmark files:")
    for bf in sorted(benchmark_files):
        count = 0
        with open(bf, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    request = json.loads(line)
                    # Add source file info for tracking
                    request["_source_file"] = bf.name
                    all_requests.append(request)
                    count += 1
        print(f"  - {bf.name}: {count} records")
    
    return all_requests


def random_sample(requests: list[dict], sample_size: int, seed: int | None = None) -> list[dict]:
    """Get a random sample of requests."""
    if seed is not None:
        random.seed(seed)
    
    if sample_size >= len(requests):
        print(f"  Sample size ({sample_size}) >= total records ({len(requests)}), using all records")
        return requests.copy()
    
    return random.sample(requests, sample_size)


def analyze_sample(sample: list[dict]) -> dict:
    """Analyze the composition of the sample."""
    stats = {
        "by_grade": {},
        "by_type": {},
        "by_difficulty": {},
        "by_source": {},
    }
    
    for req in sample:
        grade = req.get("grade", "unknown")
        qtype = req.get("type", "unknown")
        difficulty = req.get("difficulty", "unknown")
        source = req.get("_source_file", "unknown")
        
        stats["by_grade"][grade] = stats["by_grade"].get(grade, 0) + 1
        stats["by_type"][qtype] = stats["by_type"].get(qtype, 0) + 1
        stats["by_difficulty"][difficulty] = stats["by_difficulty"].get(difficulty, 0) + 1
        stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
    
    return stats


async def run_pipeline(requests: list[dict], verbose: bool = False) -> list[dict]:
    """Run the agentic pipeline on requests."""
    from agentic_pipeline_sdk import generate_one_agentic
    
    results = []
    success_count = 0
    
    for i, request in enumerate(requests):
        skills = request.get("skills", {})
        grade = request.get("grade", "?")
        qtype = request.get("type", "?")
        difficulty = request.get("difficulty", "?")
        standard_id = skills.get("substandard_id", "unknown")
        
        print(f"\n[{i+1}/{len(requests)}] Grade {grade} | {qtype} | {difficulty}")
        print(f"         Standard: {standard_id}")
        
        try:
            result = await generate_one_agentic(request, verbose=verbose)
            
            if result.get("success"):
                success_count += 1
                generated = result.get("generatedContent", {}).get("generated_content", [])
                if generated:
                    item = generated[0]
                    results.append({
                        "success": True,
                        "id": item.get("id", ""),
                        "content": item.get("content", {}),
                        "request": {k: v for k, v in request.items() if not k.startswith("_")},
                        "source_file": request.get("_source_file", ""),
                    })
                    print(f"         ✓ Generated successfully")
                else:
                    results.append({
                        "success": False,
                        "error": "No content in response",
                        "request": {k: v for k, v in request.items() if not k.startswith("_")},
                        "source_file": request.get("_source_file", ""),
                    })
                    print(f"         ✗ No content in response")
            else:
                error = result.get("error", "Unknown error")
                results.append({
                    "success": False,
                    "error": error,
                    "request": {k: v for k, v in request.items() if not k.startswith("_")},
                    "source_file": request.get("_source_file", ""),
                    "raw_response": result.get("raw_response", "")[:500] if result.get("raw_response") else "",
                })
                print(f"         ✗ {error[:80]}")
        
        except Exception as e:
            results.append({
                "success": False,
                "error": str(e),
                "request": {k: v for k, v in request.items() if not k.startswith("_")},
                "source_file": request.get("_source_file", ""),
            })
            print(f"         ✗ Exception: {str(e)[:80]}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Test pipeline on random sample from all benchmarks"
    )
    parser.add_argument(
        "--sample-size", "-n",
        type=int,
        default=200,
        help="Number of random samples to test (default: 200)",
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=ROOT / "outputs" / "random_sample_results.json",
        help="Output file for results",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show sample statistics without running pipeline",
    )
    parser.add_argument(
        "--save-sample",
        type=Path,
        default=None,
        help="Save the sampled data to a JSONL file (for reuse)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed SDK output",
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("Random Sample Pipeline Test")
    print("=" * 70)
    
    # Check API key
    if not args.dry_run:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("\nError: ANTHROPIC_API_KEY not set in environment or .env file")
            print("Set it in agent_sdk_v2/.env or export ANTHROPIC_API_KEY=...")
            sys.exit(1)
        print(f"\nAPI Key: {'*' * 10}...{api_key[-4:]}")
    
    # Load all benchmarks
    data_dir = ROOT / "data"
    print(f"\nLoading benchmarks from: {data_dir}")
    all_requests = load_all_benchmarks(data_dir)
    print(f"\nTotal records across all benchmarks: {len(all_requests)}")
    
    # Random sample
    print(f"\nTaking random sample of {args.sample_size} records...")
    if args.seed:
        print(f"  Using seed: {args.seed}")
    sample = random_sample(all_requests, args.sample_size, args.seed)
    
    # Analyze sample
    print(f"\nSample composition:")
    stats = analyze_sample(sample)
    
    print("\n  By Grade:")
    for grade, count in sorted(stats["by_grade"].items()):
        pct = count / len(sample) * 100
        print(f"    Grade {grade}: {count} ({pct:.1f}%)")
    
    print("\n  By Type:")
    for qtype, count in sorted(stats["by_type"].items()):
        pct = count / len(sample) * 100
        print(f"    {qtype}: {count} ({pct:.1f}%)")
    
    print("\n  By Difficulty:")
    for diff, count in sorted(stats["by_difficulty"].items()):
        pct = count / len(sample) * 100
        print(f"    {diff}: {count} ({pct:.1f}%)")
    
    # Save sample if requested
    if args.save_sample:
        args.save_sample.parent.mkdir(parents=True, exist_ok=True)
        with open(args.save_sample, "w", encoding="utf-8") as f:
            for req in sample:
                # Remove internal tracking fields
                clean_req = {k: v for k, v in req.items() if not k.startswith("_")}
                f.write(json.dumps(clean_req) + "\n")
        print(f"\nSample saved to: {args.save_sample}")
    
    if args.dry_run:
        print("\n[Dry run - not running pipeline]")
        return
    
    # Run pipeline
    print(f"\n{'=' * 70}")
    print("Running Pipeline")
    print("=" * 70)
    
    results = asyncio.run(run_pipeline(sample, args.verbose))
    
    # Calculate final stats
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count
    
    # Success by category
    success_by_grade = {}
    success_by_type = {}
    success_by_difficulty = {}
    
    for r in results:
        req = r.get("request", {})
        grade = req.get("grade", "unknown")
        qtype = req.get("type", "unknown")
        difficulty = req.get("difficulty", "unknown")
        is_success = r.get("success", False)
        
        if grade not in success_by_grade:
            success_by_grade[grade] = {"success": 0, "total": 0}
        success_by_grade[grade]["total"] += 1
        if is_success:
            success_by_grade[grade]["success"] += 1
        
        if qtype not in success_by_type:
            success_by_type[qtype] = {"success": 0, "total": 0}
        success_by_type[qtype]["total"] += 1
        if is_success:
            success_by_type[qtype]["success"] += 1
        
        if difficulty not in success_by_difficulty:
            success_by_difficulty[difficulty] = {"success": 0, "total": 0}
        success_by_difficulty[difficulty]["total"] += 1
        if is_success:
            success_by_difficulty[difficulty]["success"] += 1
    
    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "generated_content": [r for r in results if r.get("success")],
        "errors": [r for r in results if not r.get("success")],
        "metadata": {
            "sample_size": len(sample),
            "seed": args.seed,
            "total": len(results),
            "success": success_count,
            "failed": fail_count,
            "success_rate": f"{success_count / len(results) * 100:.1f}%",
            "success_by_grade": {
                g: f"{d['success']}/{d['total']} ({d['success']/d['total']*100:.0f}%)"
                for g, d in sorted(success_by_grade.items())
            },
            "success_by_type": {
                t: f"{d['success']}/{d['total']} ({d['success']/d['total']*100:.0f}%)"
                for t, d in sorted(success_by_type.items())
            },
            "success_by_difficulty": {
                d: f"{data['success']}/{data['total']} ({data['success']/data['total']*100:.0f}%)"
                for d, data in sorted(success_by_difficulty.items())
            },
            "timestamp": datetime.now().isoformat(),
            "source_files": list(stats["by_source"].keys()),
        },
    }
    args.output.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("Results Summary")
    print("=" * 70)
    print(f"\nTotal: {len(results)}")
    print(f"Success: {success_count} ({success_count/len(results)*100:.1f}%)")
    print(f"Failed: {fail_count} ({fail_count/len(results)*100:.1f}%)")
    
    print("\nSuccess rate by Grade:")
    for grade, data in sorted(success_by_grade.items()):
        rate = data["success"] / data["total"] * 100
        print(f"  Grade {grade}: {data['success']}/{data['total']} ({rate:.0f}%)")
    
    print("\nSuccess rate by Type:")
    for qtype, data in sorted(success_by_type.items()):
        rate = data["success"] / data["total"] * 100
        print(f"  {qtype}: {data['success']}/{data['total']} ({rate:.0f}%)")
    
    print("\nSuccess rate by Difficulty:")
    for diff, data in sorted(success_by_difficulty.items()):
        rate = data["success"] / data["total"] * 100
        print(f"  {diff}: {data['success']}/{data['total']} ({rate:.0f}%)")
    
    print(f"\nResults saved to: {args.output}")
    
    # Show sample errors if any
    if fail_count > 0:
        print(f"\nSample errors ({min(5, fail_count)} of {fail_count}):")
        for err in output_data["errors"][:5]:
            req = err.get("request", {})
            skills = req.get("skills", {})
            print(f"  - {skills.get('substandard_id', '?')} ({req.get('type', '?')}/{req.get('difficulty', '?')})")
            print(f"    Error: {err.get('error', 'Unknown')[:80]}")


if __name__ == "__main__":
    main()
