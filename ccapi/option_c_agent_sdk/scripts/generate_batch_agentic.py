#!/usr/bin/env python3
"""
Batch generate Grade 3 ELA MCQs using TRULY AGENTIC approach.

In this mode, Claude autonomously decides:
1. When to look up curriculum data
2. When to populate missing curriculum data  
3. How to use the context to generate MCQs

This is different from the original pipeline where Python hardcodes the workflow.

Usage:
  From ccapi root:
    python option_c_agent_sdk/scripts/generate_batch_agentic.py [--benchmark PATH] [--limit N] [--concurrency N]

  Env: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add ccapi root to path
ROOT = Path(__file__).resolve().parents[2]  # ccapi/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

# Import from ccapi
from ccapi.config import CCAPI_BENCHMARK_PATH
from ccapi.formatters import benchmark_row_to_request

# Import agentic pipeline
from option_c_agent_sdk.src.agentic_pipeline import (
    generate_one_agentic,
    generate_one_agentic_simple,
)


def _default_benchmark() -> Path:
    """Get default benchmark path."""
    data_dir = Path(__file__).parent.parent / "data"
    benchmark_path = data_dir / "grade-3-ela-benchmark.jsonl"
    if benchmark_path.exists():
        return benchmark_path
    if CCAPI_BENCHMARK_PATH and CCAPI_BENCHMARK_PATH.exists():
        return CCAPI_BENCHMARK_PATH
    return ROOT.parent / "edullm-ela-experiment" / "grade-3-ela-benchmark.jsonl"


def load_mcq_requests(benchmark_path: Path, limit: int | None) -> list[dict]:
    """Load MCQ requests from benchmark JSONL file."""
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


async def generate_one_with_semaphore(
    semaphore: asyncio.Semaphore,
    request: dict,
    curriculum_path: Path,
    index: int,
    total: int,
    use_simple: bool = False,
) -> dict:
    """Generate one MCQ with concurrency control."""
    substandard_id = (request.get("skills") or {}).get("substandard_id", "")
    difficulty = request.get("difficulty", "")
    
    async with semaphore:
        print(f"[{index+1}/{total}] 🤖 Claude deciding workflow for {substandard_id} ({difficulty})...")
        
        try:
            # Use the agentic generation function
            if use_simple:
                result = await generate_one_agentic_simple(request, curriculum_path=curriculum_path)
            else:
                result = await generate_one_agentic(request, curriculum_path=curriculum_path)
            
            # Log what tools Claude used (if tracked)
            tools_used = result.get("tools_used", [])
            if tools_used:
                tool_names = [t.get("name", "?") for t in tools_used]
                print(f"    └─ Tools used: {', '.join(tool_names)}")
            
            return {
                "request": request,
                "result": result,
                "success": result.get("success", False),
                "error": result.get("error"),
            }
        except Exception as e:
            print(f"[{index+1}/{total}] ✗ Error: {e}")
            return {
                "request": request,
                "result": None,
                "success": False,
                "error": str(e),
            }


async def run(
    benchmark_path: Path,
    output_path: Path,
    limit: int | None,
    concurrency: int = 3,
    use_simple: bool = False,
) -> None:
    """Run batch generation with agentic approach."""
    print("=" * 60)
    print("TRULY AGENTIC MCQ Generation")
    print("Claude decides when to call tools!")
    print("=" * 60)
    print(f"Benchmark: {benchmark_path}")
    print(f"Output: {output_path}")
    print(f"Limit: {limit if limit else 'None (all rows)'}")
    print(f"Concurrency: {concurrency}")
    print(f"Mode: {'Simple (Read/Bash)' if use_simple else 'Full (Custom MCP Tools)'}")
    print("=" * 60)
    
    # Load requests
    requests = load_mcq_requests(benchmark_path, limit)
    if not requests:
        print("Error: No MCQ rows found in benchmark.")
        sys.exit(1)
    
    print(f"\nLoaded {len(requests)} MCQ requests\n")
    
    # Curriculum path
    curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    # Create semaphore (lower concurrency for agentic to avoid rate limits)
    semaphore = asyncio.Semaphore(concurrency)
    
    # Generate all MCQs
    tasks = [
        generate_one_with_semaphore(
            semaphore, req, curriculum_path, i, len(requests), use_simple
        )
        for i, req in enumerate(requests)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Collect results
    all_items = []
    errors = []
    generation_mode = None
    
    for res in results:
        request = res["request"]
        result = res["result"]
        success = res["success"]
        
        if generation_mode is None and result:
            generation_mode = result.get("generation_mode")
        
        if success and result:
            items = result.get("generatedContent", {}).get("generated_content", [])
            for item in items:
                item["evaluation"] = None
                all_items.append(item)
        else:
            error = res.get("error", "Unknown error")
            substandard_id = (request.get("skills") or {}).get("substandard_id", "")
            print(f"✗ Failed: {substandard_id} - {error}")
            errors.append({"request": request, "error": error})
    
    # Create output
    payload = {
        "benchmark": str(benchmark_path),
        "limit": limit,
        "total_requested": len(requests),
        "total_generated": len(all_items),
        "generation_mode": generation_mode or "agentic",
        "errors": errors,
        "generated_content": all_items,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    
    print("\n" + "=" * 60)
    print("Agentic Batch Generation Complete")
    print("=" * 60)
    print(f"Total requested: {len(requests)}")
    print(f"Total generated: {len(all_items)}")
    print(f"Errors: {len(errors)}")
    print(f"Generation mode: {generation_mode or 'agentic'}")
    print(f"Output: {output_path}")
    print("=" * 60)
    
    await asyncio.sleep(0.1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Batch generate MCQs using TRULY AGENTIC approach (Claude decides tool usage)"
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=None,
        help="Path to benchmark JSONL file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Limit number of items (default: 5, lower for agentic testing)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent requests (default: 3, lower for agentic)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Use simple mode (Read/Bash tools) instead of custom MCP tools",
    )
    
    args = parser.parse_args()
    
    benchmark_path = args.benchmark or _default_benchmark()
    output_path = args.output or (ROOT / "option_c_agent_sdk" / "outputs" / "batch_agentic.json")
    
    if not benchmark_path.exists():
        print(f"Error: Benchmark file not found: {benchmark_path}")
        sys.exit(1)
    
    async def run_with_args():
        await run(benchmark_path, output_path, args.limit, args.concurrency, args.simple)
    
    try:
        import anyio
        try:
            anyio.run(run_with_args, backend="asyncio")
        except (RuntimeError, asyncio.CancelledError) as e:
            if "cancel scope" not in str(e).lower() and "event loop" not in str(e).lower():
                raise
    except ImportError:
        # Fallback to asyncio
        def exception_handler(loop, context):
            exception = context.get("exception")
            if exception:
                exc_str = str(exception)
                if "cancel scope" in exc_str.lower() or "event loop" in exc_str.lower():
                    return
            if loop.default_exception_handler:
                loop.default_exception_handler(context)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(exception_handler)
        
        try:
            loop.run_until_complete(run_with_args())
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()


if __name__ == "__main__":
    main()
