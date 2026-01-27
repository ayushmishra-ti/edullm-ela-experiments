#!/usr/bin/env python3
"""
Batch generate ELA questions using AGENTIC approach.

Claude autonomously decides when to:
1. Look up curriculum data
2. Populate missing curriculum data
3. Generate questions

Usage:
  python scripts/generate_batch.py [--input PATH] [--output PATH] [--limit N] [--type TYPE] [--verbose]

Example:
  python scripts/generate_batch.py --limit 5 --verbose
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

# Check for API key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("Error: ANTHROPIC_API_KEY not set in environment or .env file", file=sys.stderr)
    sys.exit(1)


def load_benchmark(path: Path) -> list[dict]:
    """Load benchmark JSONL file."""
    requests = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                requests.append(json.loads(line))
    return requests


async def generate_one_agentic_wrapper(request: dict, verbose: bool = False) -> dict:
    """
    Wrapper to call agentic pipeline.
    
    Claude autonomously decides when to call tools:
    - lookup_curriculum: to get assessment boundaries and misconceptions
    - populate_curriculum: to generate missing curriculum data
    """
    from agentic_pipeline import generate_one_agentic
    
    # Paths for curriculum and scripts
    curriculum_path = ROOT / ".claude" / "skills" / "ela-question-generation" / "references" / "curriculum.md"
    if not curriculum_path.exists():
        curriculum_path = ROOT / "data" / "curriculum.md"
    
    scripts_dir = ROOT / ".claude" / "skills" / "ela-question-generation" / "scripts"
    
    result = await generate_one_agentic(
        request,
        curriculum_path=curriculum_path,
        scripts_dir=scripts_dir,
        verbose=verbose,
    )
    
    # Extract the generated item from the result
    if result.get("success"):
        generated_content = result.get("generatedContent", {}).get("generated_content", [])
        if generated_content:
            item = generated_content[0]
            return {
                "success": True,
                "id": item.get("id", ""),
                "content": item.get("content", {}),
                "request": request,
                "tools_used": result.get("tools_used", []),
            }
    
    return {
        "success": False,
        "error": result.get("error", "Unknown error"),
        "request": request,
        "tools_used": result.get("tools_used", []),
    }


async def run_batch_generation(
    requests: list[dict],
    verbose: bool = False,
) -> list[dict]:
    """Run batch generation sequentially (to avoid rate limits)."""
    results = []
    
    for i, request in enumerate(requests):
        item_id = f"{request.get('skills', {}).get('substandard_id', 'unknown')}_{request.get('type', 'mcq')}_{request.get('difficulty', 'easy')}"
        print(f"\n  [{i+1}/{len(requests)}] {item_id}")
        
        result = await generate_one_agentic_wrapper(request, verbose)
        results.append(result)
        
        # Show tool calls (Claude's decisions)
        tools_used = result.get("tools_used", [])
        if tools_used:
            tool_names = [t.get("name", "unknown") for t in tools_used]
            print(f"      [CLAUDE TOOLS] {' → '.join(tool_names)}")
        
        if result.get("success"):
            print(f"      → ✓ Generated successfully")
        else:
            error = result.get('error', 'Unknown error')
            print(f"      → ✗ {error[:100]}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Batch generate ELA questions (AGENTIC)")
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=ROOT / "data" / "grade-3-ela-benchmark.jsonl",
        help="Input benchmark JSONL file",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=ROOT / "outputs" / "batch_generated.json",
        help="Output JSON file",
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
        help="Filter by question type",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed Claude tool calls and reasoning",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("AGENTIC ELA Question Generation")
    print("=" * 60)
    print("\nClaude autonomously decides when to:")
    print("  1. lookup_curriculum - get assessment boundaries & misconceptions")
    print("  2. populate_curriculum - generate missing curriculum data")
    print("  3. Generate the question using curriculum context")
    print()
    
    # Show model being used
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    print(f"Model: {model}")
    
    # Load benchmark
    print(f"Loading benchmark from: {args.input}")
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    requests = load_benchmark(args.input)
    print(f"Loaded {len(requests)} requests")
    
    # Filter by type
    if args.type != "all":
        requests = [r for r in requests if r.get("type") == args.type]
        print(f"Filtered to {len(requests)} {args.type} requests")
    
    # Limit
    if args.limit:
        requests = requests[:args.limit]
        print(f"Limited to {len(requests)} requests")
    
    if args.verbose:
        print("\nVerbose mode: ON (showing Claude's tool decisions)")
    
    # Generate using agentic approach
    print(f"\nGenerating {len(requests)} questions (Claude orchestrates)...")
    
    results = asyncio.run(run_batch_generation(requests, args.verbose))
    
    # Count successes
    success_count = sum(1 for r in results if r.get("success"))
    
    # Collect tool usage stats
    all_tools = []
    for r in results:
        all_tools.extend([t.get("name") for t in r.get("tools_used", [])])
    
    tool_counts = {}
    for tool in all_tools:
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
    
    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "generated_content": [r for r in results if r.get("success")],
        "errors": [r for r in results if not r.get("success")],
        "metadata": {
            "total": len(requests),
            "success": success_count,
            "failed": len(requests) - success_count,
            "type_filter": args.type,
            "generation_mode": "agentic",
            "tool_calls": tool_counts,
            "timestamp": datetime.now().isoformat(),
        },
    }
    
    args.output.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    
    print(f"\n{'='*60}")
    print("Generation Complete")
    print(f"{'='*60}")
    print(f"Total: {len(requests)}")
    print(f"Success: {success_count}")
    print(f"Failed: {len(requests) - success_count}")
    print(f"\nClaude's tool usage:")
    for tool, count in tool_counts.items():
        print(f"  - {tool}: {count} calls")
    print(f"\nOutput saved to: {args.output}")


if __name__ == "__main__":
    main()
