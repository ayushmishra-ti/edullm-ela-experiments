"""
InceptBench evaluation for generated ELA MCQs.

Uses InceptBench CLI (python -m inceptbench evaluate).
Converts 0–1 scores to 0–100 and attaches evaluation to each item.
Evaluation is non-fatal: pipeline succeeds even if InceptBench fails.

No API key required - uses the CLI method.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .formatters import to_inceptbench_item

logger = logging.getLogger(__name__)


def _scale_score(score: float | None) -> float | None:
    """Convert 0–1 to 0–100. None stays None."""
    if score is None:
        return None
    try:
        return round(float(score) * 100, 2)
    except (TypeError, ValueError):
        return None


def _extract_evaluation_data(data: dict, item_id: str) -> dict | None:
    """
    Extract full evaluation data from inceptbench CLI output.
    
    Returns full evaluation dict with all metrics, or None if not found.
    """
    # Try evaluations[id] format
    ev = data.get("evaluations") or {}
    if isinstance(ev, dict) and item_id in ev:
        return ev[item_id]
    
    # Try results[0] format
    res = data.get("results") or []
    if isinstance(res, list) and res and isinstance(res[0], dict):
        return res[0]
    
    # Try top-level format (single evaluation)
    if "overall" in data or "content_type" in data:
        return data
    
    return None


def _run_inceptbench_cli_sync(incept_item: dict, timeout: int = 120) -> dict | None:
    """
    Run inceptbench evaluate on one item via CLI (synchronous).
    
    Returns full evaluation dict or None on failure.
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
            )
            
            if result.returncode != 0:
                logger.warning(f"InceptBench CLI returned non-zero exit code {result.returncode} for {item_id}")
                if result.stderr:
                    logger.debug(f"InceptBench stderr: {result.stderr}")
                return None
                    
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning(f"InceptBench CLI error for {item_id}: {e}")
            return None

        if not out_path.exists():
            logger.warning(f"InceptBench output file not found for {item_id}: {out_path}")
            return None
            
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse InceptBench output JSON for {item_id}: {e}")
            return None

    eval_data = _extract_evaluation_data(data, item_id)
    if not eval_data:
        logger.warning(f"No evaluation data found in InceptBench output for {item_id}")
        return None
    
    return eval_data


async def evaluate_item(item: dict) -> dict | None:
    """
    Evaluate one generated item with InceptBench using CLI.

    item: { "id", "content": {...}, "request": {...} }

    Returns:
        Evaluation dict with overall (score 0–100, rating), dimensions, etc.;
        or None if disabled/failed.
    """
    # Convert item to InceptBench format
    incept_item = to_inceptbench_item(item, content_as_string=True)
    
    item_id = item.get("id", "")
    if not incept_item.get("content", ""):
        logger.warning(f"Empty content for item {item_id}")
        return None

    try:
        # Run CLI in executor to avoid blocking
        loop = asyncio.get_event_loop()
        eval_data = await loop.run_in_executor(
            None, 
            _run_inceptbench_cli_sync, 
            incept_item
        )
        
        if not eval_data:
            return None
        
        # Extract overall score and rating
        overall = eval_data.get("overall") or {}
        overall_score = overall.get("score")
        
        # Build evaluation dict with all available data
        eval_dict = {
            "content_type": eval_data.get("content_type"),
            "overall": {
                "score": overall_score,
                "score_100": _scale_score(overall_score),
                "rating": overall.get("rating") or overall.get("overall_rating"),
                "reasoning": overall.get("reasoning"),
                "suggested_improvements": overall.get("suggested_improvements"),
            },
        }
        
        # Add standard metrics if available
        for metric_name in ["factual_accuracy", "educational_accuracy", "localization_quality"]:
            metric = eval_data.get(metric_name) or {}
            if metric:
                eval_dict[metric_name] = {
                    "score": metric.get("score"),
                    "score_100": _scale_score(metric.get("score")),
                    "reasoning": metric.get("reasoning"),
                }
        
        # Add any other metrics/dimensions
        dimensions = {}
        for key, value in eval_data.items():
            if key not in ["content_type", "overall", "factual_accuracy", 
                          "educational_accuracy", "localization_quality",
                          "subcontent_evaluations", "evaluations", "results"]:
                if isinstance(value, dict) and "score" in value:
                    dimensions[key] = {
                        "score": value.get("score"),
                        "score_100": _scale_score(value.get("score")),
                        "reasoning": value.get("reasoning"),
                    }
        
        if dimensions:
            eval_dict["dimensions"] = dimensions
        
        return eval_dict
            
    except Exception as e:
        logger.warning(f"InceptBench evaluation error for item {item_id}: {e}")
        logger.debug(f"Error details: {type(e).__name__}: {e}", exc_info=True)
        return None


async def evaluate_batch(items: list[dict]) -> list[dict | None]:
    """
    Evaluate a list of items using InceptBench CLI.
    Each item is evaluated separately. Failures yield None.

    items: list of { "id", "content", "request" }
    """
    results = []
    for it in items:
        results.append(await evaluate_item(it))
    return results
