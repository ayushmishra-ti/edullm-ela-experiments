#!/usr/bin/env python3
"""
Test the deployed Cloud Run endpoint with random samples.

Usage:
  python scripts/test_cloud_endpoint.py --sample-size 100 --output outputs/cloud_results.json
  python scripts/test_cloud_endpoint.py --endpoint https://your-service.run.app --sample-size 50

Example:
  python scripts/test_cloud_endpoint.py --sample-size 100
  python scripts/evaluate_batch.py -i outputs/cloud_results.json
"""

from __future__ import annotations

import argparse


import asyncio
import json
import random
import sys
import time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]

# Default Cloud Run endpoint
DEFAULT_ENDPOINT = "https://inceptagentic-skill-mcq-v2-lanzf3jtla-uc.a.run.app"


def load_benchmarks() -> list[dict]:
    """Load all benchmark files and combine."""
    data_dir = ROOT / "data"
    all_items = []
    
    for jsonl_file in data_dir.glob("grade-*-ela-benchmark.jsonl"):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        item = json.loads(line)
                        item["source_file"] = jsonl_file.name
                        all_items.append(item)
                    except json.JSONDecodeError:
                        continue
    
    return all_items


async def call_endpoint(
    session: aiohttp.ClientSession,
    endpoint: str,
    request: dict,
    index: int,
    total: int,
    verbose: bool = False,
) -> dict:
    """Call the cloud endpoint for one request."""
    url = f"{endpoint.rstrip('/')}/generate"
    
    # Build the request payload (matching GenerateRequest model)
    skills = request.get("skills", {})
    payload = {
        "grade": str(request.get("grade", "3")),
        "subject": request.get("subject", "ela"),
        "type": request.get("type", "mcq"),
        "difficulty": request.get("difficulty", "medium"),
        "locale": request.get("locale", "en-US"),
        "curriculum": request.get("curriculum", "common core"),
        "skills": {
            "substandard_id": skills.get("substandard_id", ""),
            "substandard_description": skills.get("substandard_description", ""),
            "lesson_title": skills.get("lesson_title"),
        },
    }
    
    standard_id = skills.get("substandard_id", "")
    qtype = request.get("type", "mcq")
    difficulty = request.get("difficulty", "medium")
    
    print(f"  [{index+1}/{total}] {standard_id} ({qtype}, {difficulty})...", end=" ", flush=True)
    
    try:
        start = time.time()
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            elapsed = time.time() - start
            
            if resp.status != 200:
                error_text = await resp.text()
                error_preview = error_text[:300] if error_text else "No error message"
                print(f"FAIL ({resp.status}) {elapsed:.1f}s")
                if verbose and error_text:
                    print(f"    Error: {error_preview}")
                return {
                    "success": False,
                    "error": f"HTTP {resp.status}: {error_preview}",
                    "request": request,
                }
            
            data = await resp.json()
            
            # Extract the generated content (endpoint returns {"generated_content": [...]})
            generated = data.get("generated_content", [])
            if not generated:
                # Try alternative format
                generated = data.get("generatedContent", {}).get("generated_content", [])
            
            if generated:
                raw = generated[0]
                # Endpoint returns: id, request, content
                # We need to add curriculum at top level to match agent_sdk schema
                curriculum_value = request.get("curriculum", "common core").replace(" ", "_")
                
                result = {
                    "success": True,
                    "id": raw.get("id", ""),
                    "curriculum": curriculum_value,
                    "content": raw.get("content", {}),
                    "request": raw.get("request", {
                        "type": request.get("type", "mcq"),
                        "grade": str(request.get("grade", "3")),
                        "locale": request.get("locale", "en-US"),
                        "skills": {
                            "lesson_title": skills.get("lesson_title") or "",
                            "substandard_id": skills.get("substandard_id", ""),
                            "substandard_description": skills.get("substandard_description", ""),
                        },
                        "subject": request.get("subject", "ela"),
                        "difficulty": request.get("difficulty", "medium"),
                    }),
                }
                print(f"OK {elapsed:.1f}s")
                return result
            else:
                print(f"FAIL (no content) {elapsed:.1f}s")
                return {
                    "success": False,
                    "error": "No generated content in response",
                    "request": request,
                    "raw_response": str(data)[:500],
                }
                
    except asyncio.TimeoutError:
        print("FAIL (timeout)")
        return {
            "success": False,
            "error": "Request timeout (120s)",
            "request": request,
        }
    except Exception as e:
        print(f"FAIL ({type(e).__name__})")
        return {
            "success": False,
            "error": str(e),
            "request": request,
        }


async def run_tests(
    endpoint: str,
    items: list[dict],
    concurrency: int,
    verbose: bool = False,
) -> list[dict]:
    """Run all tests with concurrency limit."""
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    
    async with aiohttp.ClientSession() as session:
        async def bounded_call(item, idx):
            async with semaphore:
                # Small delay to avoid rate limiting
                if idx > 0:
                    await asyncio.sleep(0.5)
                return await call_endpoint(session, endpoint, item, idx, len(items), verbose)
        
        tasks = [bounded_call(item, i) for i, item in enumerate(items)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle exceptions
    final_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            final_results.append({
                "success": False,
                "error": str(r),
                "request": items[i],
            })
        else:
            final_results.append(r)
    
    return final_results


def main():
    parser = argparse.ArgumentParser(description="Test deployed Cloud Run endpoint")
    parser.add_argument(
        "--endpoint", "-e",
        type=str,
        default=DEFAULT_ENDPOINT,
        help=f"Cloud Run endpoint URL (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--sample-size", "-n",
        type=int,
        default=100,
        help="Number of random samples to test (default: 100)",
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
        default=ROOT / "outputs" / "cloud_results.json",
        help="Output JSON file (default: outputs/cloud_results.json)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=2,
        help="Number of concurrent requests (default: 2, reduce if getting 503 errors)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show sample composition without calling endpoint",
    )
    args = parser.parse_args()
    
    # Load and sample
    print(f"Loading benchmarks from {ROOT / 'data'}...")
    all_items = load_benchmarks()
    print(f"Loaded {len(all_items)} items from benchmark files")
    
    if args.seed is not None:
        random.seed(args.seed)
        print(f"Random seed: {args.seed}")
    
    sample_size = min(args.sample_size, len(all_items))
    samples = random.sample(all_items, sample_size)
    
    # Show composition
    print(f"\nSample composition ({sample_size} items):")
    by_type = {}
    by_grade = {}
    by_standard = {}
    for item in samples:
        qtype = item.get("type", "unknown")
        grade = item.get("grade", "unknown")
        std_family = (item.get("skills", {}).get("substandard_id", "") or "").split(".")[2] if len((item.get("skills", {}).get("substandard_id", "") or "").split(".")) > 2 else "unknown"
        by_type[qtype] = by_type.get(qtype, 0) + 1
        by_grade[grade] = by_grade.get(grade, 0) + 1
        by_standard[std_family] = by_standard.get(std_family, 0) + 1
    
    print(f"  By type: {dict(sorted(by_type.items()))}")
    print(f"  By grade: {dict(sorted(by_grade.items(), key=lambda x: str(x[0])))}")
    print(f"  By standard: {dict(sorted(by_standard.items()))}")
    
    if args.dry_run:
        print("\nDry run - not calling endpoint")
        return
    
    # Run tests
    print(f"\nTesting endpoint: {args.endpoint}")
    print(f"Concurrency: {args.concurrency}")
    print()
    
    start_time = time.time()
    results = asyncio.run(run_tests(args.endpoint, samples, args.concurrency, args.verbose))
    elapsed = time.time() - start_time
    
    # Count results
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count
    
    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    # Filter successful results; save id, curriculum, content, request (match agent_sdk schema)
    successful_results = [
        {
            "id": r["id"],
            "curriculum": r.get("curriculum", "common_core"),
            "content": r["content"],
            "request": r["request"],
        }
        for r in results if r.get("success")
    ]
    output_data = {"generated_content": successful_results}
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Summary
    print(f"\n{'='*60}")
    print("Test Complete")
    print(f"{'='*60}")
    print(f"Total requests: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Success rate: {100*success_count/len(results):.1f}%")
    print(f"Total time: {elapsed:.1f}s")
    print(f"Avg time per request: {elapsed/len(results):.1f}s")
    print(f"\nResults saved to: {args.output}")
    print(f"\nTo evaluate:")
    print(f"  python scripts/evaluate_batch.py -i {args.output}")


if __name__ == "__main__":
    main()
