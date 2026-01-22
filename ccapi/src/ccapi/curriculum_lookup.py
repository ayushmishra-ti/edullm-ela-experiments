"""
Curriculum lookup tool.

This module provides a function to search the curriculum.md file for a given
substandard_id and return assessment boundaries and common misconceptions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def parse_curriculum_entry(text: str) -> dict[str, Any]:
    """
    Parse a single curriculum entry from the markdown format.
    
    Returns:
        {
            "standard_id": str,
            "standard_description": str,
            "assessment_boundaries": str | None,
            "common_misconceptions": list[str] | None
        }
    """
    result = {
        "standard_id": None,
        "standard_description": None,
        "assessment_boundaries": None,
        "common_misconceptions": None,
    }
    
    # Extract Standard ID
    std_id_match = re.search(r"^Standard ID:\s*(.+)$", text, re.MULTILINE)
    if std_id_match:
        result["standard_id"] = std_id_match.group(1).strip()
    
    # Extract Standard Description
    std_desc_match = re.search(r"^Standard Description:\s*(.+)$", text, re.MULTILINE)
    if std_desc_match:
        result["standard_description"] = std_desc_match.group(1).strip()
    
    # Extract Assessment Boundaries
    # Look for "Assessment Boundaries:" and capture until "Common Misconceptions:"
    ab_match = re.search(
        r"^Assessment Boundaries:\s*(.*?)(?=^Common Misconceptions:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if ab_match:
        ab_text = ab_match.group(1).strip()
        # Remove "*None specified*" and empty lines
        ab_text = re.sub(r"^\*\s*None specified\s*\*$", "", ab_text, flags=re.MULTILINE)
        ab_text = ab_text.strip()
        if ab_text:
            result["assessment_boundaries"] = ab_text
    
    # Extract Common Misconceptions
    # Look for "Common Misconceptions:" and capture until "Difficulty Definitions:"
    cm_match = re.search(
        r"^Common Misconceptions:\s*(.*?)(?=^Difficulty Definitions:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if cm_match:
        cm_text = cm_match.group(1).strip()
        # Remove "*None specified*"
        cm_text = re.sub(r"^\*\s*None specified\s*\*$", "", cm_text, flags=re.MULTILINE)
        cm_text = cm_text.strip()
        if cm_text:
            # Split by bullet points (lines starting with *)
            misconceptions = [
                line.strip()
                for line in cm_text.split("\n")
                if line.strip().startswith("*") and not line.strip().startswith("*None")
            ]
            # Clean up bullet markers
            misconceptions = [m.lstrip("*").strip() for m in misconceptions if m.strip()]
            if misconceptions:
                result["common_misconceptions"] = misconceptions
    
    return result


def lookup_curriculum(substandard_id: str, curriculum_path: Path | None = None) -> dict[str, Any]:
    """
    Search curriculum.md for a given substandard_id and return assessment boundaries
    and common misconceptions.
    
    Args:
        substandard_id: The standard ID to search for (e.g., "CCSS.ELA-LITERACY.L.3.1.A")
        curriculum_path: Path to curriculum.md file. If None, tries to find it.
    
    Returns:
        {
            "found": bool,
            "standard_id": str | None,
            "standard_description": str | None,
            "assessment_boundaries": str | None,
            "common_misconceptions": list[str] | None
        }
    """
    if curriculum_path is None:
        # Try to find curriculum.md in common locations
        # First try: option_c_agent_sdk/data/curriculum.md
        root = Path(__file__).resolve().parents[2]  # Go up to ccapi/
        curriculum_path = root / "option_c_agent_sdk" / "data" / "curriculum.md"
        if not curriculum_path.exists():
            # Fallback: data/curriculum.md in root
            curriculum_path = root / "data" / "curriculum.md"
    
    if not curriculum_path.exists():
        return {
            "found": False,
            "standard_id": None,
            "standard_description": None,
            "assessment_boundaries": None,
            "common_misconceptions": None,
            "error": f"Curriculum file not found: {curriculum_path}",
        }
    
    try:
        content = curriculum_path.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "found": False,
            "standard_id": None,
            "standard_description": None,
            "assessment_boundaries": None,
            "common_misconceptions": None,
            "error": f"Failed to read curriculum file: {e}",
        }
    
    # Split by "---" separator to get individual entries
    entries = content.split("---")
    
    # Search for the matching standard_id
    for entry in entries:
        parsed = parse_curriculum_entry(entry)
        if parsed["standard_id"] == substandard_id:
            return {
                "found": True,
                "standard_id": parsed["standard_id"],
                "standard_description": parsed["standard_description"],
                "assessment_boundaries": parsed["assessment_boundaries"],
                "common_misconceptions": parsed["common_misconceptions"],
            }
    
    # Not found
    return {
        "found": False,
        "standard_id": substandard_id,
        "standard_description": None,
        "assessment_boundaries": None,
        "common_misconceptions": None,
        "error": f"Standard ID '{substandard_id}' not found in curriculum",
    }
