#!/usr/bin/env python3
"""
Batch generate Grade 3 ELA MCQs using TRULY AGENTIC approach with Claude Agent SDK.

This script uses the fully agentic pipeline where Claude autonomously decides:
- When to look up curriculum data
- When to populate missing curriculum data  
- How to use the context to generate MCQs

All tools (lookup_curriculum, populate_curriculum) are called by Claude automatically,
not pre-called by Python code. This matches the agentic workflow shown in the docs.

Usage:
  From ccapi root:
    python option_c_agent_sdk/scripts/generate_batch_agent_sdk.py [--benchmark PATH] [--limit N] [--concurrency N] [--evaluate]

  Env: ANTHROPIC_API_KEY
  Benchmark: grade-3-ela-benchmark.jsonl; default from option_c_agent_sdk/data/grade-3-ela-benchmark.jsonl
  
  Evaluation:
    Use --evaluate to run InceptBench evaluation on generated items.
    Requires: pip install inceptbench (Python 3.11-3.13)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add ccapi root to path so option_c_agent_sdk can be imported
ROOT = Path(__file__).resolve().parents[2]  # ccapi/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Also add src for ccapi imports
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

# Import from ccapi
from ccapi.config import CCAPI_BENCHMARK_PATH
from ccapi.formatters import benchmark_row_to_request, to_inceptbench_item

# Import from option_c_agent_sdk - use agentic pipeline
from option_c_agent_sdk import generate_one_agentic


def _extract_score(data: dict, item_id: str) -> tuple[float | None, float | None, str | None]:
    """Parse inceptbench output. Returns (overall_score 0-1, overall_score_100, rating)."""
    score, score_100, rating = None, None, None

    # evaluations[id].overall.score
    ev = data.get("evaluations") or {}
    if isinstance(ev, dict) and item_id in ev:
        ov = (ev[item_id] or {}).get("overall") or {}
        if isinstance(ov, dict):
            s = ov.get("score")
            if s is not None:
                try:
                    score = float(s)
                    score_100 = round(score * 100, 2)
                except (TypeError, ValueError):
                    pass
            rating = ov.get("rating") or ov.get("overall_rating")

    # results[0].overall.score
    if score is None:
        res = data.get("results") or []
        if isinstance(res, list) and res and isinstance(res[0], dict):
            ov = (res[0] or {}).get("overall") or {}
            if isinstance(ov, dict):
                s = ov.get("score")
                if s is not None:
                    try:
                        score = float(s)
                        score_100 = round(score * 100, 2)
                    except (TypeError, ValueError):
                        pass
                rating = ov.get("rating") or ov.get("overall_rating")

    # overall.score (single eval)
    if score is None:
        ov = data.get("overall") or {}
        if isinstance(ov, dict):
            s = ov.get("score")
            if s is not None:
                try:
                    score = float(s)
                    score_100 = round(score * 100, 2)
                except (TypeError, ValueError):
                    pass
            rating = ov.get("rating") or ov.get("overall_rating")

    return (score, score_100, rating)


def run_inceptbench_cli(incept_item: dict, timeout: int = 120, verbose: bool = False) -> dict | None:
    """
    Run inceptbench evaluate on one item via CLI. Returns
    { "overall_score", "overall_score_100", "rating" } or None on failure.
    """
    payload = {"generated_content": [incept_item]}
    item_id = incept_item.get("id", "")

    with tempfile.TemporaryDirectory(prefix="incept_") as td:
        in_path = Path(td) / "in.json"
        out_path = Path(td) / "out.json"
        in_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        
        cmd = [sys.executable, "-m", "inceptbench", "evaluate", str(in_path), "-o", str(out_path)]
        if verbose:
            cmd.append("--verbose")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ROOT),
            )
            
            if result.returncode != 0:
                print(f"  ⚠ Inceptbench returned non-zero exit code {result.returncode} for {item_id}")
                if result.stderr:
                    print(f"  Error: {result.stderr[:200]}")
                return None
                    
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            print(f"  ⚠ Inceptbench subprocess error for {item_id}: {e}")
            return None

        if not out_path.exists():
            print(f"  ⚠ Inceptbench output file not found for {item_id}")
            return None
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ⚠ Failed to parse inceptbench output JSON for {item_id}: {e}")
            return None

    score, score_100, rating = _extract_score(data, item_id)
    if score is None and score_100 is None:
        print(f"  ⚠ No score found in inceptbench output for {item_id}")
        return None
    return {
        "overall_score": score,
        "overall_score_100": score_100,
        "rating": rating or "",
    }


def _check_inceptbench() -> bool:
    """Check if inceptbench CLI is available."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "inceptbench", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(ROOT),
        )
        return r.returncode == 0
    except Exception:
        return False


def _default_benchmark() -> Path:
    """Get default benchmark path from data folder."""
    # Use benchmark from option_c_agent_sdk/data folder
    data_dir = Path(__file__).parent.parent / "data"
    benchmark_path = data_dir / "grade-3-ela-benchmark.jsonl"
    if benchmark_path.exists():
        return benchmark_path
    # Fallback to parent folder
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
) -> dict:
    """
    Generate one MCQ with semaphore for concurrency control.
    
    Now that we consume the entire generator (no early break), concurrent
    processing is safe and won't cause cancel-scope errors.
    """
    substandard_id = (request.get("skills") or {}).get("substandard_id", "")
    difficulty = request.get("difficulty", "")
    
    async with semaphore:
        print(f"[{index+1}/{total}] Generating {substandard_id} ({difficulty})...")
        try:
            # Use agentic pipeline - Claude will autonomously decide when to call tools
            result = await generate_one_agentic(request, curriculum_path=curriculum_path)
            
            return {
                "request": request,
                "result": result,
                "success": result.get("success", False),
                "error": result.get("error"),
            }
        except Exception as e:
            print(f"[{index+1}/{total}] Error generating {substandard_id}: {e}")
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
    concurrency: int = 5,
    do_evaluate: bool = False,
) -> None:
    """Run batch generation with async concurrency."""
    print("="*60)
    print("Option C: Agent SDK - Batch Generation (Fully Agentic)")
    print("="*60)
    print("Mode: AGENTIC - Claude autonomously decides when to call tools")
    print("  - Claude will call lookup_curriculum tool when needed")
    print("  - Claude will call populate_curriculum tool if data is missing")
    print("  - All tool calls are made by Claude, not pre-called by Python")
    print("="*60)
    print(f"Benchmark: {benchmark_path}")
    print(f"Output: {output_path}")
    print(f"Limit: {limit if limit else 'None (all rows)'}")
    print(f"Concurrency: {concurrency}")
    print(f"Evaluation: {'Yes' if do_evaluate else 'No'}")
    print("="*60)
    
    # Check inceptbench if evaluation is requested
    if do_evaluate:
        if not _check_inceptbench():
            print("Error: inceptbench CLI not found. Install with: pip install inceptbench")
            print("(inceptbench requires Python 3.11-3.13; see https://pypi.org/project/inceptbench/)")
            sys.exit(1)
        print("✓ inceptbench CLI check passed")
    
    # Load requests
    requests = load_mcq_requests(benchmark_path, limit)
    if not requests:
        print("Error: No MCQ rows found in benchmark.")
        sys.exit(1)
    
    print(f"\nLoaded {len(requests)} MCQ requests from benchmark\n")
    
    # Curriculum path from data folder
    curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)
    
    # Generate all MCQs concurrently
    # Safe now because we consume entire generators (no early break)
    tasks = [
        generate_one_with_semaphore(semaphore, req, curriculum_path, i, len(requests))
        for i, req in enumerate(requests)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Collect results in the same format as generate_batch.py
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
                # Evaluate with inceptbench if requested
                evaluation = None
                if do_evaluate:
                    item_id = item.get("id", "")
                    print(f"  Evaluating {item_id}...")
                    incept_item = to_inceptbench_item(item, content_as_string=True)
                    ev = run_inceptbench_cli(incept_item, verbose=False)
                    if ev:
                        evaluation = ev
                        score_100 = ev.get("overall_score_100")
                        if score_100 is not None:
                            print(f"  ✓ Score: {score_100}%")
                        else:
                            print(f"  ⚠ Evaluation completed but no score")
                    else:
                        print(f"  ✗ Evaluation failed")
                
                item["evaluation"] = evaluation
                all_items.append(item)
        else:
            error = res.get("error", "Unknown error")
            substandard_id = (request.get("skills") or {}).get("substandard_id", "")
            print(f"✗ Failed: {substandard_id} - {error}")
            errors.append({"request": request, "error": error})
    
    # Create output in the same format as generate_batch.py
    payload = {
        "benchmark": str(benchmark_path),
        "limit": limit,
        "total_requested": len(requests),
        "total_generated": len(all_items),
        "generation_mode": generation_mode or "agentic",
        "errors": errors,
        "generated_content": all_items,
    }
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    
    print("\n" + "="*60)
    print("Batch Generation Complete")
    print("="*60)
    print(f"Total requested: {len(requests)}")
    print(f"Total generated: {len(all_items)}")
    print(f"Errors: {len(errors)}")
    print(f"Generation mode: {generation_mode or 'agent_sdk'}")
    
    # Evaluation statistics
    if do_evaluate:
        evaluated = [item for item in all_items if item.get("evaluation") is not None]
        scores_100 = [
            float(item["evaluation"]["overall_score_100"])
            for item in evaluated
            if item.get("evaluation", {}).get("overall_score_100") is not None
        ]
        if scores_100:
            avg_score = round(sum(scores_100) / len(scores_100), 2)
            pass_count = sum(1 for s in scores_100 if s > 85)
            pass_rate = round(100.0 * pass_count / len(scores_100), 1)
            print(f"Evaluated: {len(evaluated)}/{len(all_items)}")
            print(f"Average score: {avg_score}%")
            print(f"Pass rate (>85%): {pass_rate}% ({pass_count}/{len(scores_100)})")
        else:
            print(f"Evaluated: {len(evaluated)}/{len(all_items)} (no scores)")
    
    print(f"Output saved to: {output_path}")
    print("="*60)
    
    # Small wait to ensure all background cleanup completes
    await asyncio.sleep(0.1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Batch generate MCQs using Agent SDK with async concurrency"
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=None,
        help="Path to benchmark JSONL file (default: option_c_agent_sdk/data/grade-3-ela-benchmark.jsonl)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit number of items to process (default: 10)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Number of concurrent requests (default: 5)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output JSON file path (default: option_c_agent_sdk/outputs/batch_generated.json)",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run InceptBench evaluation on generated items",
    )
    
    args = parser.parse_args()
    
    # Set defaults
    benchmark_path = args.benchmark or _default_benchmark()
    output_path = args.output or (ROOT / "option_c_agent_sdk" / "outputs" / "batch_generated.json")
    
    if not benchmark_path.exists():
        print(f"Error: Benchmark file not found: {benchmark_path}")
        sys.exit(1)
    
    # Create the async function to run
    async def run_with_args():
        await run(benchmark_path, output_path, args.limit, args.concurrency, args.evaluate)
    
    # Use anyio.run() with asyncio backend for proper async cleanup
    # This is critical: anyio.run() with backend="asyncio" ensures all cancel scopes
    # and async generators are cleaned up in the same task context
    try:
        import anyio
        
        # Force asyncio backend - this ensures anyio uses the same event loop
        # semantics as asyncio, preventing cancel-scope/task mismatches
        try:
            anyio.run(run_with_args, backend="asyncio")
        except (RuntimeError, asyncio.CancelledError) as e:
            # Suppress cleanup errors that escape anyio.run()
            error_msg = str(e)
            if "cancel scope" in error_msg.lower() or "event loop is closed" in error_msg.lower():
                # Harmless cleanup error - ignore it completely
                pass
            else:
                # Real error - re-raise
                raise
        except Exception as e:
            # Catch any other cleanup-related exceptions
            error_msg = str(e)
            if "cancel scope" in error_msg.lower() or "transport" in error_msg.lower():
                # Harmless cleanup error - ignore it
                pass
            else:
                # Real error - re-raise
                raise
        
    except ImportError:
        # Fallback: use asyncio with comprehensive cleanup
        # This handles the case where anyio is not installed
        def exception_handler(loop, context):
            """
            Suppress ALL harmless SDK cleanup errors from background tasks.
            
            The SDK's async generators create background tasks for cleanup.
            These tasks may try to exit cancel scopes after the main task completes,
            causing harmless RuntimeErrors that we can safely ignore.
            """
            exception = context.get("exception")
            message = context.get("message", "")
            
            # Suppress ALL cancel scope and event loop cleanup errors
            if exception:
                exc_str = str(exception)
                exc_type = type(exception).__name__
                
                # Suppress ANY cancel scope errors (most common)
                if "cancel scope" in exc_str.lower():
                    return  # Suppress completely - this is always harmless
                
                # Suppress event loop closed errors
                if "event loop is closed" in exc_str.lower():
                    return  # Suppress completely
                
                # Suppress CancelledError (from cleanup)
                if exc_type == "CancelledError":
                    return  # Suppress completely - cleanup cancellation
            
                # Suppress RuntimeError with cleanup-related messages
                if exc_type == "RuntimeError":
                    if "event loop" in exc_str.lower() or "transport" in exc_str.lower():
                        return  # Suppress cleanup-related RuntimeErrors
            
            # Suppress "Task exception was never retrieved" messages
            if "Task exception was never retrieved" in message or "unhandled exception" in message.lower():
                if exception:
                    exc_str = str(exception)
                    if "cancel scope" in exc_str.lower() or "event loop" in exc_str.lower():
                        return  # Suppress completely
            
            # Suppress "Exception ignored" messages for cleanup
            if "Exception ignored" in message:
                if exception:
                    exc_str = str(exception)
                    if "event loop" in exc_str.lower() or "transport" in exc_str.lower():
                        return  # Suppress cleanup-related ignored exceptions
            
            # For real errors, use the default handler
            if loop.default_exception_handler:
                loop.default_exception_handler(context)

        # Create a new event loop with our exception handler
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(exception_handler)
        
        try:
            # Run the main coroutine
            loop.run_until_complete(run_with_args())
            
            # CRITICAL: Wait for all async generators to shutdown
            # This gives the SDK's async generators time to clean up properly
            loop.run_until_complete(loop.shutdown_asyncgens())
            
            # Wait a bit more for any remaining background tasks
            pending = asyncio.all_tasks(loop)
            if pending:
                # Wait for tasks to complete (with timeout to avoid hanging)
                try:
                    loop.run_until_complete(
                        asyncio.wait(pending, timeout=0.5, return_when=asyncio.ALL_COMPLETED)
                    )
                except asyncio.TimeoutError:
                    # Some tasks didn't complete - cancel them
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    # Wait for cancellation to complete
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
        finally:
            # Final cleanup: cancel any remaining tasks and close the loop
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                if pending:
                    for task in pending:
                        task.cancel()
                    # Wait for cancellation
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                # Ignore errors during final cleanup
                pass
            finally:
                loop.close()


if __name__ == "__main__":
    main()
