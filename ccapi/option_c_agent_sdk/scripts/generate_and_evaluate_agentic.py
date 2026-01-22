#!/usr/bin/env python3
"""
Generate 100 MCQs using fully agentic process, then evaluate with multithreading.

This script:
1. Generates 100 MCQs using fully agentic approach (Claude autonomously calls tools)
2. Then evaluates all generated items using multithreading for speed

Usage:
  From ccapi root:
    python option_c_agent_sdk/scripts/generate_and_evaluate_agentic.py [--benchmark PATH] [--limit N] [--gen-concurrency N] [--eval-concurrency N]

  Env: ANTHROPIC_API_KEY
  Requires: pip install inceptbench (Python 3.11-3.13) for evaluation
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def run_inceptbench_cli_sync(incept_item: dict, timeout: int = 120) -> dict | None:
    """
    Run inceptbench evaluate on one item via CLI (synchronous for threading).
    Returns { "overall_score", "overall_score_100", "rating" } or None on failure.
    """
    payload = {"generated_content": [incept_item]}
    item_id = incept_item.get("id", "")

    with tempfile.TemporaryDirectory(prefix="incept_") as td:
        in_path = Path(td) / "in.json"
        out_path = Path(td) / "out.json"
        in_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        
        cmd = [sys.executable, "-m", "inceptbench", "evaluate", str(in_path), "-o", str(out_path)]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ROOT),
            )
            
            if result.returncode != 0:
                return None
                    
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

        if not out_path.exists():
            return None
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    score, score_100, rating = _extract_score(data, item_id)
    if score is None and score_100 is None:
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


async def generate_one_with_semaphore(
    semaphore: asyncio.Semaphore,
    request: dict,
    curriculum_path: Path,
    index: int,
    total: int,
) -> dict:
    """
    Generate one MCQ with semaphore for concurrency control.
    
    Uses fully agentic approach - Claude autonomously decides when to call tools.
    """
    substandard_id = (request.get("skills") or {}).get("substandard_id", "")
    difficulty = request.get("difficulty", "")
    
    async with semaphore:
        print(f"\n[{index+1}/{total}] Generating {substandard_id} ({difficulty})...")
        try:
            # Use agentic pipeline - Claude will autonomously decide when to call tools
            result = await generate_one_agentic(request, curriculum_path=curriculum_path)
            print(f"[{index+1}/{total}] ✓ Completed {substandard_id}\n")
            
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


def evaluate_item_threaded(item: dict, index: int, total: int) -> tuple[int, dict, dict | None]:
    """
    Evaluate one item using inceptbench (runs in thread pool).
    
    Returns: (index, item, evaluation_result)
    """
    item_id = item.get("id", "")
    print(f"  [{index+1}/{total}] Evaluating {item_id}...")
    
    incept_item = to_inceptbench_item(item, content_as_string=True)
    ev = run_inceptbench_cli_sync(incept_item, timeout=120)
    
    if ev:
        score_100 = ev.get("overall_score_100")
        if score_100 is not None:
            print(f"  [{index+1}/{total}] ✓ {item_id}: {score_100}%")
        else:
            print(f"  [{index+1}/{total}] ⚠ {item_id}: Evaluation completed but no score")
    else:
        print(f"  [{index+1}/{total}] ✗ {item_id}: Evaluation failed")
    
    return (index, item, ev)


async def run(
    benchmark_path: Path,
    output_path: Path,
    limit: int | None,
    gen_concurrency: int = 3,
    eval_concurrency: int = 10,
) -> None:
    """
    Run batch generation (agentic) then evaluation (multithreaded).
    
    Phase 1: Generate MCQs using fully agentic approach (Claude calls tools)
    Phase 2: Evaluate all generated items using multithreading
    """
    print("="*60)
    print("Option C: Agent SDK - Generate & Evaluate (Fully Agentic)")
    print("="*60)
    print("Mode: AGENTIC - Claude autonomously decides when to call tools")
    print("  - Claude will call lookup_curriculum tool when needed")
    print("  - Claude will call populate_curriculum tool if data is missing")
    print("  - All tool calls are made by Claude, not pre-called by Python")
    print("="*60)
    print(f"Benchmark: {benchmark_path}")
    print(f"Output: {output_path}")
    print(f"Limit: {limit if limit else 'None (all rows)'}")
    print(f"Generation concurrency: {gen_concurrency}")
    print(f"Evaluation concurrency: {eval_concurrency}")
    print("="*60)
    
    # Check inceptbench
    if not _check_inceptbench():
        print("Error: inceptbench CLI not found. Install with: pip install inceptbench")
        print("(inceptbench requires Python 3.11-3.13; see https://pypi.org/project/inceptbench/)")
        sys.exit(1)
    print("✓ inceptbench CLI check passed\n")
    
    # Load requests
    requests = load_mcq_requests(benchmark_path, limit)
    if not requests:
        print("Error: No MCQ rows found in benchmark.")
        sys.exit(1)
    
    print(f"Loaded {len(requests)} MCQ requests from benchmark\n")
    
    # Curriculum path from data folder
    curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    # ========================================================================
    # PHASE 1: Generate MCQs using fully agentic approach
    # ========================================================================
    print("="*60)
    print("PHASE 1: Generating MCQs (Fully Agentic)")
    print("="*60)
    
    # Create semaphore for generation concurrency (lower for agentic)
    semaphore = asyncio.Semaphore(gen_concurrency)
    
    # Generate all MCQs concurrently
    tasks = [
        generate_one_with_semaphore(semaphore, req, curriculum_path, i, len(requests))
        for i, req in enumerate(requests)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Collect generated items
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
                # Evaluation will be added in Phase 2
                item["evaluation"] = None
                all_items.append(item)
        else:
            error = res.get("error", "Unknown error")
            substandard_id = (request.get("skills") or {}).get("substandard_id", "")
            print(f"✗ Failed: {substandard_id} - {error}")
            errors.append({"request": request, "error": error})
    
    print(f"\n✓ Generation complete: {len(all_items)} items generated, {len(errors)} errors\n")
    
    # ========================================================================
    # PHASE 2: Evaluate all generated items using multithreading
    # ========================================================================
    print("="*60)
    print("PHASE 2: Evaluating Generated Items (Multithreaded)")
    print("="*60)
    print(f"Evaluating {len(all_items)} items with {eval_concurrency} threads...\n")
    
    # Evaluate using ThreadPoolExecutor for true multithreading
    evaluated_items = [None] * len(all_items)
    
    with ThreadPoolExecutor(max_workers=eval_concurrency) as executor:
        # Submit all evaluation tasks
        futures = {
            executor.submit(evaluate_item_threaded, item, i, len(all_items)): i
            for i, item in enumerate(all_items)
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            try:
                index, item, evaluation = future.result()
                item["evaluation"] = evaluation
                evaluated_items[index] = item
            except Exception as e:
                original_index = futures[future]
                print(f"  ✗ Evaluation error for item {original_index}: {e}")
                evaluated_items[original_index] = all_items[original_index]
    
    # Replace all_items with evaluated items
    all_items = evaluated_items
    
    # ========================================================================
    # Save results
    # ========================================================================
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
    
    # Calculate evaluation statistics
    evaluated = [item for item in all_items if item and item.get("evaluation") is not None]
    scores_100 = [
        float(item["evaluation"]["overall_score_100"])
        for item in evaluated
        if item.get("evaluation", {}).get("overall_score_100") is not None
    ]
    
    print("\n" + "="*60)
    print("Batch Generation & Evaluation Complete")
    print("="*60)
    print(f"Total requested: {len(requests)}")
    print(f"Total generated: {len(all_items)}")
    print(f"Errors: {len(errors)}")
    print(f"Generation mode: {generation_mode or 'agentic'}")
    
    if scores_100:
        avg_score = round(sum(scores_100) / len(scores_100), 2)
        pass_count = sum(1 for s in scores_100 if s > 85)
        pass_rate = round(100.0 * pass_count / len(scores_100), 1)
        print(f"\nEvaluation Results:")
        print(f"  Evaluated: {len(evaluated)}/{len(all_items)}")
        print(f"  Average score: {avg_score}%")
        print(f"  Pass rate (>85%): {pass_rate}% ({pass_count}/{len(scores_100)})")
    else:
        print(f"\nEvaluation Results:")
        print(f"  Evaluated: {len(evaluated)}/{len(all_items)} (no scores)")
    
    print(f"\nOutput saved to: {output_path}")
    print("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate MCQs (agentic) then evaluate (multithreaded)"
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
        default=100,
        help="Limit number of items to process (default: 100)",
    )
    parser.add_argument(
        "--gen-concurrency",
        type=int,
        default=3,
        help="Concurrency for generation phase (default: 3, lower for agentic)",
    )
    parser.add_argument(
        "--eval-concurrency",
        type=int,
        default=10,
        help="Concurrency for evaluation phase using threads (default: 10)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output JSON file path (default: option_c_agent_sdk/outputs/batch_agentic_evaluated.json)",
    )
    
    args = parser.parse_args()
    
    # Set defaults
    benchmark_path = args.benchmark or _default_benchmark()
    output_path = args.output or (ROOT / "option_c_agent_sdk" / "outputs" / "batch_agentic_evaluated.json")
    
    if not benchmark_path.exists():
        print(f"Error: Benchmark file not found: {benchmark_path}")
        sys.exit(1)
    
    # Create the async function to run
    async def run_with_args():
        await run(benchmark_path, output_path, args.limit, args.gen_concurrency, args.eval_concurrency)
    
    # Use anyio.run() with asyncio backend for proper async cleanup
    try:
        import anyio
        anyio.run(run_with_args, backend="asyncio")
    except ImportError:
        # Fallback: use asyncio with comprehensive cleanup
        def exception_handler(loop, context):
            """Suppress harmless SDK cleanup errors from background tasks."""
            exception = context.get("exception")
            if exception and isinstance(exception, RuntimeError):
                msg = str(exception)
                if "cancel scope" in msg.lower() or "event loop is closed" in msg.lower():
                    return  # Suppress cleanup warnings
            loop.default_exception_handler(context)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(exception_handler)
        
        try:
            loop.run_until_complete(run_with_args())
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for t in pending:
                    t.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                loop.close()


if __name__ == "__main__":
    main()
