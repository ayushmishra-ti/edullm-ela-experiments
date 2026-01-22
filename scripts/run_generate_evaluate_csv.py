#!/usr/bin/env python3
"""
Generate MCQs from grade-3-ela-benchmark.jsonl, evaluate with inceptbench CLI,
write results to CSV and compute aggregate score.

Uses inceptbench package CLI (no httpx POST to api.inceptbench.com).
Requires: pip install inceptbench (Python 3.11-3.13).

Usage:
  python scripts/run_generate_evaluate_csv.py [--benchmark PATH] [--limit N] [--output PATH]

  Env: ANTHROPIC_API_KEY. CCAPI_ELA_MCQ_SKILL_ID optional (Skills API).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def setup_logging(log_file: Path | None = None) -> logging.Logger:
    """Set up logging to both console and file."""
    logger = logging.getLogger("run_generate_evaluate")
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler (INFO and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler (DEBUG and above)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from ccapi.config import CCAPI_BENCHMARK_PATH
from ccapi.formatters import benchmark_row_to_request, to_inceptbench_item
from ccapi.pipeline import generate_one


def _default_benchmark() -> Path:
    if CCAPI_BENCHMARK_PATH and CCAPI_BENCHMARK_PATH.exists():
        return CCAPI_BENCHMARK_PATH
    return ROOT.parent / "edullm-ela-experiment" / "grade-3-ela-benchmark.jsonl"


def load_mcq_requests(benchmark_path: Path, limit: int | None) -> list[dict]:
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


def run_inceptbench_cli(incept_item: dict, timeout: int = 120, verbose: bool = True, logger: logging.Logger | None = None) -> dict | None:
    """
    Run inceptbench evaluate on one item via CLI. Returns
    { "overall_score", "overall_score_100", "rating" } or None on failure.
    
    Args:
        incept_item: The item to evaluate
        timeout: Timeout in seconds
        verbose: Enable verbose logging in inceptbench
        logger: Logger instance for capturing inceptbench output
    """
    payload = {"generated_content": [incept_item]}
    item_id = incept_item.get("id", "")

    with tempfile.TemporaryDirectory(prefix="incept_") as td:
        in_path = Path(td) / "in.json"
        out_path = Path(td) / "out.json"
        in_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        
        cmd = [sys.executable, "-m", "inceptbench", "evaluate", str(in_path), "-o", str(out_path)]
        if verbose:
            # Add verbose flag - try --verbose first, common in CLI tools
            # If inceptbench uses a different flag, the error message will show in logs
            cmd.append("--verbose")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ROOT),
            )
            
            # Always log inceptbench output if logger provided (helps debug failures)
            if logger:
                if result.stdout:
                    logger.debug(f"Inceptbench stdout for {item_id}:\n{result.stdout}")
                if result.stderr:
                    # stderr might contain warnings, errors, or verbose output
                    if result.returncode != 0:
                        logger.warning(f"Inceptbench stderr for {item_id}:\n{result.stderr}")
                    else:
                        # Even on success, stderr might contain verbose logging
                        logger.debug(f"Inceptbench stderr for {item_id}:\n{result.stderr}")
                if result.returncode != 0:
                    logger.warning(f"Inceptbench returned non-zero exit code {result.returncode} for {item_id}")
                    # Log the command that failed for debugging
                    logger.debug(f"Failed command: {' '.join(cmd)}")
                    
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            if logger:
                logger.error(f"Inceptbench subprocess error for {item_id}: {e}")
            return None

        if not out_path.exists():
            if logger:
                logger.warning(f"Inceptbench output file not found for {item_id}: {out_path}")
            return None
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            if logger:
                logger.error(f"Failed to parse inceptbench output JSON for {item_id}: {e}")
            return None

    score, score_100, rating = _extract_score(data, item_id)
    if score is None and score_100 is None:
        if logger:
            logger.warning(f"No score found in inceptbench output for {item_id}. Output keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
        return None
    return {
        "overall_score": score,
        "overall_score_100": score_100,
        "rating": rating or "",
    }


def _check_inceptbench() -> bool:
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


async def run(
    benchmark_path: Path,
    csv_path: Path,
    limit: int | None,
    log_file: Path | None = None,
) -> None:
    logger = setup_logging(log_file)
    
    logger.info(f"Starting MCQ generation and evaluation")
    logger.info(f"Benchmark: {benchmark_path}")
    logger.info(f"Output CSV: {csv_path}")
    logger.info(f"Limit: {limit if limit else 'None (all rows)'}")
    
    if not _check_inceptbench():
        logger.error("inceptbench CLI not found. Install with: pip install inceptbench")
        logger.error("(inceptbench requires Python 3.11-3.13; see https://pypi.org/project/inceptbench/)")
        sys.exit(1)
    
    logger.debug("inceptbench CLI check passed")

    requests = load_mcq_requests(benchmark_path, limit)
    if not requests:
        logger.error("No MCQ rows in benchmark.")
        sys.exit(1)
    
    logger.info(f"Loaded {len(requests)} MCQ requests from benchmark")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    header = ["id", "substandard_id", "difficulty", "question", "gen_error", "overall_score", "overall_score_100", "rating", "eval_error"]
    rows: list[dict[str, str | float | None]] = []
    scores_100: list[float] = []
    all_items: list[dict] = []
    errors: list[dict] = []
    generation_mode: str | None = None

    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        w = csv.DictWriter(cf, fieldnames=header, extrasaction="ignore")
        w.writeheader()

        for i, req in enumerate(requests):
            sid = (req.get("skills") or {}).get("substandard_id", "")
            diff = req.get("difficulty", "")
            logger.info(f"[{i+1}/{len(requests)}] Processing {sid} ({diff})")

            logger.debug(f"Request: {json.dumps(req, indent=2)}")
            res = await generate_one(req)
            
            if generation_mode is None:
                generation_mode = res.get("generation_mode")
                logger.info(f"Generation mode: {generation_mode}")
            
            if not res.get("success"):
                error_msg = res.get("error", "unknown")
                logger.warning(f"Generation failed for {sid} ({diff}): {error_msg}")
                row = {
                    "id": "",
                    "substandard_id": sid,
                    "difficulty": diff,
                    "question": "",
                    "gen_error": res.get("error", "unknown"),
                    "overall_score": "",
                    "overall_score_100": "",
                    "rating": "",
                    "eval_error": "not_evaluated",
                }
                w.writerow(row)
                rows.append(row)
                errors.append({"request": req, "error": res.get("error", "unknown")})
                continue

            items = res.get("generatedContent", {}).get("generated_content", [])
            if not items:
                logger.warning(f"No items generated for {sid} ({diff})")
                row = {"id": "", "substandard_id": sid, "difficulty": diff, "question": "", "gen_error": "no_item", "overall_score": "", "overall_score_100": "", "rating": "", "eval_error": "not_evaluated"}
                w.writerow(row)
                rows.append(row)
                errors.append({"request": req, "error": "no_item"})
                continue
            
            logger.debug(f"Generated {len(items)} item(s) for {sid}")

            for it in items:
                item_id = it.get("id", "")
                all_items.append({"id": item_id, "content": it.get("content"), "request": req, "evaluation": None})
                q = (it.get("content") or {}).get("question", "") or ""
                q_short = (q[:120] + "…") if len(q) > 120 else q
                logger.debug(f"Evaluating item {item_id}")
                
                incept = to_inceptbench_item(it, content_as_string=True)
                ev = run_inceptbench_cli(incept, verbose=True, logger=logger)

                if ev is None:
                    logger.warning(f"Evaluation failed for {item_id} ({sid})")
                    row = {
                        "id": it.get("id", ""),
                        "substandard_id": sid,
                        "difficulty": diff,
                        "question": q_short,
                        "gen_error": "",
                        "overall_score": "",
                        "overall_score_100": "",
                        "rating": "",
                        "eval_error": "inceptbench_failed",
                    }
                    w.writerow(row)
                    rows.append(row)
                else:
                    s100 = ev.get("overall_score_100")
                    if s100 is not None:
                        scores_100.append(float(s100))
                        logger.debug(f"Item {item_id} scored {s100}%")
                    else:
                        logger.warning(f"Item {item_id} evaluated but no score returned")
                    
                    row = {
                        "id": it.get("id", ""),
                        "substandard_id": sid,
                        "difficulty": diff,
                        "question": q_short,
                        "gen_error": "",
                        "overall_score": ev.get("overall_score") if ev.get("overall_score") is not None else "",
                        "overall_score_100": ev.get("overall_score_100") if ev.get("overall_score_100") is not None else "",
                        "rating": ev.get("rating") if ev.get("rating") is not None else "",
                        "eval_error": "",
                    }
                    w.writerow(row)
                    rows.append(row)

    # Aggregate
    n_total = len(rows)
    n_evaluated = len(scores_100)
    aggregate_score = round(sum(scores_100) / n_evaluated, 2) if n_evaluated else None
    pass_count = sum(1 for s in scores_100 if s > 85)
    pass_rate = round(100.0 * pass_count / n_evaluated, 1) if n_evaluated else None
    n_failed_gen = sum(1 for r in rows if r.get("gen_error"))
    n_failed_eval = sum(1 for r in rows if r.get("eval_error") == "inceptbench_failed")

    logger.info("=" * 60)
    logger.info("GENERATION AND EVALUATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total requests: {n_total}")
    logger.info(f"Successfully generated: {len(all_items)}")
    logger.info(f"Generation failures: {n_failed_gen}")
    logger.info(f"Successfully evaluated: {n_evaluated}")
    logger.info(f"Evaluation failures: {n_failed_eval}")
    logger.info(f"Aggregate score: {aggregate_score}%")
    logger.info(f"Pass rate (score > 85%): {pass_rate}%")
    logger.info(f"Generation mode: {generation_mode}")

    summary = {
        "n_total": n_total,
        "n_evaluated": n_evaluated,
        "aggregate_score": aggregate_score,
        "pass_rate_percent": pass_rate,
        "n_failed_generation": n_failed_gen,
        "n_failed_evaluation": n_failed_eval,
        "generation_mode": generation_mode,
        "timestamp": datetime.now().isoformat(),
    }
    summary_path = csv_path.with_name(csv_path.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(f"Summary saved: {summary_path}")

    batch_json_path = csv_path.parent / "batch_generated.json"
    batch_payload = {
        "benchmark": str(benchmark_path.name),
        "limit": limit,
        "total_requested": len(requests),
        "total_generated": len(all_items),
        "generation_mode": generation_mode,
        "errors": errors,
        "generated_content": all_items,
        "timestamp": datetime.now().isoformat(),
    }
    batch_json_path.write_text(json.dumps(batch_payload, indent=2), encoding="utf-8")
    logger.info(f"Batch JSON saved: {batch_json_path}")
    logger.info(f"CSV saved: {csv_path}")
    
    if log_file:
        logger.info(f"Log file: {log_file}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate, evaluate with inceptbench CLI, write CSV + aggregate.")
    ap.add_argument("--benchmark", type=Path, default=None, help="Benchmark JSONL")
    ap.add_argument("--limit", type=int, default=None, help="Max MCQs")
    ap.add_argument("--output", "-o", type=Path, default=None, help="Output CSV (default: outputs/eval_results.csv)")
    ap.add_argument("--log", type=Path, default=None, help="Log file (default: outputs/generate_evaluate.log)")
    args = ap.parse_args()

    bench = args.benchmark or _default_benchmark()
    if not bench.exists():
        print(f"Benchmark not found: {bench}", file=sys.stderr)
        sys.exit(1)

    out = args.output or (ROOT / "outputs" / "eval_results.csv")
    log_file = args.log or (ROOT / "outputs" / "generate_evaluate.log")
    
    print(f"Generating + evaluating (inceptbench CLI) from {bench}, limit={args.limit}")
    print(f"Log file: {log_file}")
    asyncio.run(run(bench, out, args.limit, log_file))


if __name__ == "__main__":
    main()
