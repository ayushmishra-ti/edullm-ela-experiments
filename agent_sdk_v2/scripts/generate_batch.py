#!/usr/bin/env python3
"""
Batch generate ELA questions using the agentic pipeline SDK.

Usage:
  python scripts/generate_batch.py --input data/grade-8-ela-benchmark.jsonl
  python scripts/generate_batch.py --input data/grade-8-ela-benchmark.jsonl --limit 10
  python scripts/generate_batch.py --input data/grade-8-ela-benchmark.jsonl --type mcq --limit 5
  python scripts/generate_batch.py --dry-run  # Show what would be processed

Examples:
  # Run all grade 8 items
  python scripts/generate_batch.py -i data/grade-8-ela-benchmark.jsonl

  # Test with 5 items first
  python scripts/generate_batch.py -i data/grade-8-ela-benchmark.jsonl -n 5

  # Only MCQ questions
  python scripts/generate_batch.py -i data/grade-8-ela-benchmark.jsonl --type mcq

  # Custom output file
  python scripts/generate_batch.py -i data/grade-8-ela-benchmark.jsonl -o outputs/grade8_results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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


def load_benchmark(path: Path) -> list[dict]:
    """Load benchmark JSONL file."""
    requests = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                requests.append(json.loads(line))
    return requests


def analyze_requests(requests: list[dict]) -> dict:
    """Analyze the composition of requests."""
    stats = {
        "by_grade": {},
        "by_type": {},
        "by_difficulty": {},
    }
    
    for req in requests:
        grade = req.get("grade", "unknown")
        qtype = req.get("type", "unknown")
        difficulty = req.get("difficulty", "unknown")
        
        stats["by_grade"][grade] = stats["by_grade"].get(grade, 0) + 1
        stats["by_type"][qtype] = stats["by_type"].get(qtype, 0) + 1
        stats["by_difficulty"][difficulty] = stats["by_difficulty"].get(difficulty, 0) + 1
    
    return stats


async def generate_one(request: dict, verbose: bool = False) -> dict:
    """Generate one question using the agentic pipeline SDK."""
    from agentic_pipeline_sdk import generate_one_agentic
    
    result = await generate_one_agentic(request, verbose=verbose)
    
    if result.get("success"):
        generated_content = result.get("generatedContent", {}).get("generated_content", [])
        if generated_content:
            item = generated_content[0]
            return {
                "success": True,
                "id": item.get("id", ""),
                "content": item.get("content", {}),
                "request": request,
            }
        else:
            return {
                "success": False,
                "error": "No content in response",
                "request": request,
                "raw_response": result.get("raw_response", "")[:500] if result.get("raw_response") else "",
            }
    
    return {
        "success": False,
        "error": result.get("error", "Unknown error"),
        "request": request,
        "raw_response": result.get("raw_response", "")[:500] if result.get("raw_response") else "",
    }


async def run_batch(requests: list[dict], verbose: bool = False) -> list[dict]:
    """Run batch generation sequentially."""
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
            result = await generate_one(request, verbose=verbose)
            results.append(result)
            
            if result.get("success"):
                success_count += 1
                print(f"         ✓ Generated successfully")
            else:
                error = result.get("error", "Unknown error")
                print(f"         ✗ {error[:80]}")
        
        except Exception as e:
            results.append({
                "success": False,
                "error": str(e),
                "request": request,
            })
            print(f"         ✗ Exception: {str(e)[:80]}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Batch generate ELA questions using Agent SDK",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/generate_batch.py -i data/grade-8-ela-benchmark.jsonl
  python scripts/generate_batch.py -i data/grade-8-ela-benchmark.jsonl --limit 10
  python scripts/generate_batch.py -i data/grade-8-ela-benchmark.jsonl --type mcq
  python scripts/generate_batch.py --dry-run -i data/grade-8-ela-benchmark.jsonl
"""
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="Input benchmark JSONL file (e.g., data/grade-8-ela-benchmark.jsonl)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON file (default: outputs/<input_name>_results.json)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Limit number of items to generate",
    )
    parser.add_argument(
        "--type", "-t",
        choices=["all", "mcq", "msq", "fill-in"],
        default="all",
        help="Filter by question type (default: all)",
    )
    parser.add_argument(
        "--difficulty", "-d",
        choices=["all", "easy", "medium", "hard"],
        default="all",
        help="Filter by difficulty (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without running generation",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed SDK output",
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("ELA Question Generation - Batch Mode (Agent SDK)")
    print("=" * 70)
    
    # Check API key (unless dry-run)
    if not args.dry_run:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("\nError: ANTHROPIC_API_KEY not set in environment or .env file")
            print("Set it in agent_sdk_v2/.env or export ANTHROPIC_API_KEY=...")
            sys.exit(1)
    
    # Show model
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    print(f"\nModel: {model}")
    print(f"Skills Location: {ROOT / '.claude' / 'skills'}")
    
    # Load benchmark
    print(f"\nLoading: {args.input}")
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    requests = load_benchmark(args.input)
    print(f"Loaded {len(requests)} records")
    
    # Filter by type
    if args.type != "all":
        requests = [r for r in requests if r.get("type") == args.type]
        print(f"Filtered to {len(requests)} {args.type} records")
    
    # Filter by difficulty
    if args.difficulty != "all":
        requests = [r for r in requests if r.get("difficulty") == args.difficulty]
        print(f"Filtered to {len(requests)} {args.difficulty} records")
    
    # Limit
    if args.limit:
        requests = requests[:args.limit]
        print(f"Limited to {len(requests)} records")
    
    if not requests:
        print("\nNo records to process after filtering.")
        sys.exit(0)
    
    # Analyze composition
    print(f"\nRequest composition:")
    stats = analyze_requests(requests)
    
    print("\n  By Grade:")
    for grade, count in sorted(stats["by_grade"].items()):
        pct = count / len(requests) * 100
        print(f"    Grade {grade}: {count} ({pct:.1f}%)")
    
    print("\n  By Type:")
    for qtype, count in sorted(stats["by_type"].items()):
        pct = count / len(requests) * 100
        print(f"    {qtype}: {count} ({pct:.1f}%)")
    
    print("\n  By Difficulty:")
    for diff, count in sorted(stats["by_difficulty"].items()):
        pct = count / len(requests) * 100
        print(f"    {diff}: {count} ({pct:.1f}%)")
    
    if args.dry_run:
        print("\n[Dry run - not running generation]")
        return
    
    # Set output path
    if args.output:
        output_path = args.output
    else:
        input_stem = args.input.stem.replace("-benchmark", "")
        output_path = ROOT / "outputs" / f"{input_stem}_results.json"
    
    # Run generation
    print(f"\n{'=' * 70}")
    print(f"Generating {len(requests)} questions...")
    print("=" * 70)
    
    results = asyncio.run(run_batch(requests, args.verbose))
    
    # Calculate stats
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "generated_content": [r for r in results if r.get("success")],
        "errors": [r for r in results if not r.get("success")],
        "metadata": {
            "input_file": str(args.input),
            "total": len(requests),
            "success": success_count,
            "failed": fail_count,
            "success_rate": f"{success_count / len(results) * 100:.1f}%" if results else "0%",
            "type_filter": args.type,
            "difficulty_filter": args.difficulty,
            "limit": args.limit,
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
        },
    }
    output_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    
    # Print summary
    print(f"\n{'=' * 70}")
    print("Generation Complete")
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
    
    print(f"\nResults saved to: {output_path}")
    
    # Show sample errors if any
    if fail_count > 0:
        print(f"\nSample errors ({min(5, fail_count)} of {fail_count}):")
        for err in output_data["errors"][:5]:
            req = err.get("request", {})
            skills = req.get("skills", {})
            print(f"  - {skills.get('substandard_id', '?')} ({req.get('type', '?')}/{req.get('difficulty', '?')})")
            print(f"    Error: {err.get('error', 'Unknown')[:80]}")
    
    # Hint for evaluation
    print(f"\n{'=' * 70}")
    print("Next step: Evaluate the results")
    print("=" * 70)
    print(f"  python scripts/evaluate_batch.py -i {output_path}")


if __name__ == "__main__":
    main()
