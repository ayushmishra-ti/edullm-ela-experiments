#!/usr/bin/env python3
"""
Curriculum Lookup Script.

Usage:
    python scripts/lookup_curriculum.py "<standard_id>"

Example:
    python scripts/lookup_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A"
"""

import json
import re
import sys
from pathlib import Path


def parse_curriculum_entry(text: str) -> dict:
    """Parse a single curriculum entry."""
    result = {
        "standard_id": None,
        "standard_description": None,
        "assessment_boundaries": None,
        "common_misconceptions": None,
    }
    
    std_id_match = re.search(r"^Standard ID:\s*(.+)$", text, re.MULTILINE)
    if std_id_match:
        result["standard_id"] = std_id_match.group(1).strip()
    
    std_desc_match = re.search(r"^Standard Description:\s*(.+)$", text, re.MULTILINE)
    if std_desc_match:
        result["standard_description"] = std_desc_match.group(1).strip()
    
    ab_match = re.search(
        r"^Assessment Boundaries:\s*(.*?)(?=^Common Misconceptions:|\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    if ab_match:
        ab_text = ab_match.group(1).strip()
        ab_text = re.sub(r"^\*\s*None specified\s*\*$", "", ab_text, flags=re.MULTILINE).strip()
        if ab_text:
            result["assessment_boundaries"] = ab_text
    
    cm_match = re.search(
        r"^Common Misconceptions:\s*(.*?)(?=^Difficulty Definitions:|\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    if cm_match:
        cm_text = cm_match.group(1).strip()
        cm_text = re.sub(r"^\*\s*None specified\s*\*$", "", cm_text, flags=re.MULTILINE).strip()
        if cm_text:
            misconceptions = [
                m.lstrip("*").strip() for m in cm_text.split("\n")
                if m.strip().startswith("*") and not m.strip().startswith("*None")
            ]
            if misconceptions:
                result["common_misconceptions"] = misconceptions
    
    return result


def lookup_curriculum(standard_id: str) -> dict:
    """Search curriculum.md for a standard."""
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "data" / "curriculum.md",
        Path.cwd() / "data" / "curriculum.md",
    ]
    
    curriculum_path = None
    for path in possible_paths:
        if path.exists():
            curriculum_path = path
            break
    
    if not curriculum_path:
        return {"found": False, "error": "Curriculum file not found"}
    
    content = curriculum_path.read_text(encoding="utf-8")
    entries = content.split("---")
    
    for entry in entries:
        parsed = parse_curriculum_entry(entry)
        if parsed["standard_id"] == standard_id:
            return {"found": True, **{k: v for k, v in parsed.items() if v is not None}}
    
    return {"found": False, "standard_id": standard_id, "error": "Standard not found"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python lookup_curriculum.py <standard_id>"}))
        sys.exit(1)
    
    print(json.dumps(lookup_curriculum(sys.argv[1]), indent=2))
