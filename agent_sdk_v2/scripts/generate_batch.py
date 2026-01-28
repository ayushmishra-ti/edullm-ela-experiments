#!/usr/bin/env python3
"""
Batch generate ELA questions using the v2 agentic pipeline.

Architecture:
- SDK reads SKILL.md files as the single source of truth
- Only one tool: generate_passage (via SDK, not Python API scripts)
- No curriculum lookup/populate tools

Usage:
  python scripts/generate_batch.py --limit 5
  python scripts/generate_batch.py --input data/benchmark.jsonl --limit 10
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


async def generate_one(request: dict, verbose: bool = False) -> dict:
    """Generate one question using the agentic pipeline."""
    from agentic_pipeline import generate_one_agentic
    
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
                "tools_used": result.get("tools_used", []),
            }
    
    return {
        "success": False,
        "error": result.get("error", "Unknown error"),
        "request": request,
        "tools_used": result.get("tools_used", []),
    }


async def run_batch(requests: list[dict], verbose: bool = False) -> list[dict]:
    """Run batch generation sequentially."""
    results = []
    
    for i, request in enumerate(requests):
        skills = request.get("skills", {})
        item_id = f"{skills.get('substandard_id', 'unknown')}_{request.get('type', 'mcq')}_{request.get('difficulty', 'easy')}"
        print(f"\n  [{i+1}/{len(requests)}] {item_id}")
        
        result = await generate_one(request, verbose)
        results.append(result)
        
        # Show tool calls
        tools_used = result.get("tools_used", [])
        if tools_used:
            tool_names = [t.get("name", "unknown") for t in tools_used]
            print(f"      [TOOLS] {' → '.join(tool_names)}")
        
        if result.get("success"):
            print(f"      → ✓ Generated successfully")
        else:
            error = result.get('error', 'Unknown error')
            print(f"      → ✗ {error[:100]}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Batch generate ELA questions (v2 SDK)")
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=ROOT / "data" / "benchmark.jsonl",
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
        help="Show detailed output",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("ELA Question Generation (v2 SDK)")
    print("=" * 60)
    print("\nArchitecture:")
    print("  - SKILL.md files are the single source of truth")
    print("  - Only tool: generate_passage (via SDK)")
    print("  - No curriculum lookup/populate tools")
    print()
    
    # Show model
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    print(f"Model: {model}")
    
    # Load benchmark
    print(f"Loading benchmark from: {args.input}")
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        print(f"\nCreate a benchmark file at {args.input} with JSONL format:")
        print('{"type": "mcq", "grade": "3", "difficulty": "easy", "skills": {"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A", "substandard_description": "..."}}')
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
    
    # Generate
    print(f"\nGenerating {len(requests)} questions...")
    results = asyncio.run(run_batch(requests, args.verbose))
    
    # Stats
    success_count = sum(1 for r in results if r.get("success"))
    all_tools = []
    for r in results:
        all_tools.extend([t.get("name") for t in r.get("tools_used", [])])
    
    tool_counts = {}
    for tool in all_tools:
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
    
    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "generated_content": [r for r in results if r.get("success")],
        "errors": [r for r in results if not r.get("success")],
        "metadata": {
            "total": len(requests),
            "success": success_count,
            "failed": len(requests) - success_count,
            "type_filter": args.type,
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
    if tool_counts:
        print(f"\nTool usage:")
        for tool, count in tool_counts.items():
            print(f"  - {tool}: {count} calls")
    print(f"\nOutput saved to: {args.output}")


if __name__ == "__main__":
    main()
