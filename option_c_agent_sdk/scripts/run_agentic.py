#!/usr/bin/env python3
"""
Simple script to run agentic MCQ generation.

Usage:
    python option_c_agent_sdk/scripts/run_agentic.py --limit 10
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent to path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from option_c_agent_sdk.generate import generate_mcq_agentic


def load_benchmark(benchmark_path: Path, limit: int | None) -> list[dict]:
    """Load MCQ requests from benchmark JSONL."""
    requests = []
    with open(benchmark_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("type") != "mcq":
                continue
            
            # Convert to request format
            skills = d.get("skills", {})
            if not skills:
                skills = {
                    "substandard_id": d.get("substandard_id", ""),
                    "substandard_description": d.get("substandard_description", ""),
                }
            
            request = {
                "skills": skills,
                "subject": d.get("subject", "ela"),
                "grade_level": d.get("grade_level", d.get("grade", 3)),
                "difficulty": d.get("difficulty", "easy"),
            }
            requests.append(request)
            
            if limit and len(requests) >= limit:
                break
    return requests


async def main(
    benchmark_path: Path,
    output_path: Path,
    limit: int | None,
    concurrency: int = 3,
):
    """Run agentic generation."""
    print("=" * 60)
    print("Agentic MCQ Generation (Claude Agent SDK)")
    print("=" * 60)
    print(f"Benchmark: {benchmark_path}")
    print(f"Output: {output_path}")
    print(f"Limit: {limit or 'all'}")
    print(f"Concurrency: {concurrency}")
    print("=" * 60)
    
    # Load requests
    requests = load_benchmark(benchmark_path, limit)
    if not requests:
        print("Error: No MCQ requests found")
        sys.exit(1)
    
    print(f"Loaded {len(requests)} requests\n")
    
    # Generate MCQs
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    
    async def generate_one(req: dict, idx: int):
        async with semaphore:
            print(f"\n[{idx+1}/{len(requests)}] {req['skills']['substandard_id']} ({req['difficulty']})")
            result = await generate_mcq_agentic(req, timeout_seconds=120, verbose=True)
            return {"request": req, "result": result}
    
    tasks = [generate_one(req, i) for i, req in enumerate(requests)]
    results = await asyncio.gather(*tasks)
    
    # Collect items
    all_items = []
    errors = []
    for res in results:
        if res["result"].get("success"):
            items = res["result"].get("generatedContent", {}).get("generated_content", [])
            all_items.extend(items)
        else:
            errors.append({
                "request": res["request"],
                "error": res["result"].get("error"),
            })
    
    # Save output
    output = {
        "benchmark": str(benchmark_path),
        "total_requested": len(requests),
        "total_generated": len(all_items),
        "errors": len(errors),
        "generation_mode": "agentic",
        "generated_content": all_items,
        "error_details": errors,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    
    print("\n" + "=" * 60)
    print("Complete")
    print("=" * 60)
    print(f"Generated: {len(all_items)}/{len(requests)}")
    print(f"Errors: {len(errors)}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run agentic MCQ generation")
    parser.add_argument("--benchmark", type=Path, default=None)
    parser.add_argument("--output", "-o", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=3)
    
    args = parser.parse_args()
    
    # Defaults
    benchmark = args.benchmark or (ROOT / "option_c_agent_sdk" / "data" / "grade-3-ela-benchmark.jsonl")
    output = args.output or (ROOT / "option_c_agent_sdk" / "outputs" / "agentic_results.json")
    
    if not benchmark.exists():
        print(f"Error: Benchmark not found: {benchmark}")
        sys.exit(1)
    
    # Run
    asyncio.run(main(benchmark, output, args.limit, args.concurrency))
