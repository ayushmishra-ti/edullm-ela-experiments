#!/usr/bin/env python3
"""
Curriculum Lookup Script for Agent Skills.

Usage:
    python scripts/lookup_curriculum.py "<standard_id>"

Example:
    python scripts/lookup_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A"

Returns JSON with assessment boundaries and common misconceptions.
"""

import json
import re
import sys
from pathlib import Path


def parse_curriculum_entry(text: str) -> dict:
    """Parse a single curriculum entry from markdown format."""
    result = {
        "standard_id": None,
        "standard_description": None,
        "learning_objectives": None,
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

    # Extract Learning Objectives
    lo_match = re.search(
        r"^Learning Objectives:\s*(.*?)(?=^Assessment Boundaries:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if lo_match:
        lo_text = lo_match.group(1).strip()
        lo_text = re.sub(r"^\*\s*None specified\s*\*$", "", lo_text, flags=re.MULTILINE)
        lo_text = lo_text.strip()
        if lo_text:
            result["learning_objectives"] = lo_text
    
    # Extract Assessment Boundaries
    ab_match = re.search(
        r"^Assessment Boundaries:\s*(.*?)(?=^Common Misconceptions:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if ab_match:
        ab_text = ab_match.group(1).strip()
        ab_text = re.sub(r"^\*\s*None specified\s*\*$", "", ab_text, flags=re.MULTILINE)
        ab_text = ab_text.strip()
        if ab_text:
            result["assessment_boundaries"] = ab_text
    
    # Extract Common Misconceptions
    cm_match = re.search(
        r"^Common Misconceptions:\s*(.*?)(?=^Difficulty Definitions:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if cm_match:
        cm_text = cm_match.group(1).strip()
        cm_text = re.sub(r"^\*\s*None specified\s*\*$", "", cm_text, flags=re.MULTILINE)
        cm_text = cm_text.strip()
        if cm_text:
            misconceptions = [
                line.strip()
                for line in cm_text.split("\n")
                if line.strip().startswith("*") and not line.strip().startswith("*None")
            ]
            misconceptions = [m.lstrip("*").strip() for m in misconceptions if m.strip()]
            if misconceptions:
                result["common_misconceptions"] = misconceptions
    
    return result


def lookup_curriculum(substandard_id: str) -> dict:
    """
    Search curriculum.md for a given substandard_id.
    
    Returns assessment boundaries and common misconceptions.
    """
    # Find curriculum.md - check multiple locations
    script_dir = Path(__file__).parent.parent
    possible_paths = [
        script_dir / "references" / "curriculum.md",
        script_dir.parent.parent.parent / "data" / "curriculum.md",
        Path.cwd() / "data" / "curriculum.md",
    ]
    
    curriculum_path = None
    for path in possible_paths:
        if path.exists():
            curriculum_path = path
            break
    
    if not curriculum_path:
        return {
            "found": False,
            "error": f"Curriculum file not found. Searched: {[str(p) for p in possible_paths]}",
        }
    
    try:
        content = curriculum_path.read_text(encoding="utf-8")
    except Exception as e:
        return {"found": False, "error": f"Failed to read curriculum file: {e}"}
    
    # Split by "---" separator
    entries = content.split("---")
    
    for entry in entries:
        parsed = parse_curriculum_entry(entry)
        if parsed["standard_id"] == substandard_id:
            return {
                "found": True,
                "standard_id": parsed["standard_id"],
                "standard_description": parsed["standard_description"],
                "learning_objectives": parsed["learning_objectives"],
                "assessment_boundaries": parsed["assessment_boundaries"],
                "common_misconceptions": parsed["common_misconceptions"],
                # Boolean flags for Claude to check if data needs to be populated
                "has_objectives": bool(parsed["learning_objectives"]),
                "has_boundaries": bool(parsed["assessment_boundaries"]),
                "has_misconceptions": bool(parsed["common_misconceptions"]),
            }
    
    return {
        "found": False,
        "standard_id": substandard_id,
        "error": f"Standard ID '{substandard_id}' not found in curriculum",
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Usage: python lookup_curriculum.py <standard_id>",
            "example": "python lookup_curriculum.py CCSS.ELA-LITERACY.L.3.1.A"
        }, indent=2))
        sys.exit(1)
    
    standard_id = sys.argv[1]
    result = lookup_curriculum(standard_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
