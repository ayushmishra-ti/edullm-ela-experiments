"""
Utility functions for saving outputs to the outputs folder.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def get_outputs_dir(base_path: Path | None = None) -> Path:
    """
    Get the outputs directory path.
    
    Args:
        base_path: Base path (defaults to option_c_agent_sdk folder)
    
    Returns:
        Path to outputs directory
    """
    if base_path is None:
        # Go up from src/ to option_c_agent_sdk/
        base_path = Path(__file__).parent.parent
    outputs_dir = base_path / "outputs"
    outputs_dir.mkdir(exist_ok=True)
    return outputs_dir


def save_mcq_result(
    result: dict[str, Any],
    request: dict[str, Any] | None = None,
    *,
    filename: str | None = None,
    base_path: Path | None = None,
) -> Path:
    """
    Save MCQ generation result to outputs folder.
    
    Args:
        result: Result from generate_one_agent_sdk()
        request: Original request (optional, will be extracted from result if available)
        filename: Custom filename (defaults to timestamp + standard_id)
        base_path: Base path for outputs folder
    
    Returns:
        Path to saved file
    """
    outputs_dir = get_outputs_dir(base_path)
    
    # Extract item ID for filename
    items = result.get("generatedContent", {}).get("generated_content", [])
    item_id = items[0].get("id", "unknown") if items else "unknown"
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"mcq_{item_id}_{timestamp}.json"
    
    output_file = outputs_dir / filename
    
    # Prepare output data
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "generation_mode": result.get("generation_mode"),
        "success": result.get("success"),
        "request": request or {},
        "result": result,
    }
    
    # Add generated items if available
    if items:
        output_data["generated_items"] = items
    
    output_file.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    return output_file


def save_curriculum_lookup(
    lookup_result: dict[str, Any],
    substandard_id: str,
    *,
    filename: str | None = None,
    base_path: Path | None = None,
) -> Path:
    """
    Save curriculum lookup result to outputs folder.
    
    Args:
        lookup_result: Result from lookup_curriculum()
        substandard_id: The standard ID that was looked up
        filename: Custom filename
        base_path: Base path for outputs folder
    
    Returns:
        Path to saved file
    """
    outputs_dir = get_outputs_dir(base_path)
    
    if filename is None:
        safe_id = substandard_id.replace(".", "_").replace("-", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"curriculum_lookup_{safe_id}_{timestamp}.json"
    
    output_file = outputs_dir / filename
    
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "substandard_id": substandard_id,
        "lookup_result": lookup_result,
    }
    
    output_file.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    return output_file


def save_batch_results(
    results: list[dict[str, Any]],
    *,
    filename: str | None = None,
    base_path: Path | None = None,
) -> Path:
    """
    Save batch generation results to outputs folder.
    
    Args:
        results: List of results from generate_one_agent_sdk()
        filename: Custom filename
        base_path: Base path for outputs folder
    
    Returns:
        Path to saved file
    """
    outputs_dir = get_outputs_dir(base_path)
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"batch_results_{timestamp}.json"
    
    output_file = outputs_dir / filename
    
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "total_items": len(results),
        "successful": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results,
    }
    
    output_file.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    return output_file
