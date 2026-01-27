#!/usr/bin/env python3
"""
Populate Curriculum Script.

Usage:
    python scripts/populate_curriculum.py "<standard_id>" "<standard_description>"

After running, Claude should generate the content and update curriculum.md.
"""

import json
import re
import sys
from pathlib import Path


def get_curriculum_path() -> Path:
    """Find curriculum.md."""
    paths = [
        Path(__file__).parent.parent.parent.parent / "data" / "curriculum.md",
        Path.cwd() / "data" / "curriculum.md",
    ]
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def update_curriculum_file(standard_id: str, boundaries: str, misconceptions: list) -> bool:
    """Update curriculum.md with generated content."""
    path = get_curriculum_path()
    if not path.exists():
        return False
    
    content = path.read_text(encoding="utf-8")
    parts = content.split("---")
    updated = False
    
    for i, entry in enumerate(parts):
        if f"Standard ID: {standard_id}" in entry:
            if boundaries:
                pattern = r"(Assessment Boundaries:\s*)(?:\*None specified\*|.*?)(?=\n\nCommon Misconceptions:)"
                entry = re.sub(pattern, f"\\1{boundaries.strip()}\n", entry, flags=re.DOTALL)
            
            if misconceptions:
                misc_text = "\n".join([f"* {m.strip()}" for m in misconceptions])
                pattern = r"(Common Misconceptions:\s*)(?:\*None specified\*|.*?)(?=\n\nDifficulty Definitions:)"
                entry = re.sub(pattern, f"\\1{misc_text}\n", entry, flags=re.DOTALL)
            
            parts[i] = entry
            updated = True
            break
    
    if updated:
        path.write_text("---".join(parts), encoding="utf-8")
    return updated


def main():
    if len(sys.argv) < 3:
        print(json.dumps({
            "error": "Usage: python populate_curriculum.py <standard_id> <description>",
        }))
        sys.exit(1)
    
    standard_id = sys.argv[1]
    description = sys.argv[2]
    
    print(json.dumps({
        "action": "populate_curriculum",
        "standard_id": standard_id,
        "description": description,
        "instructions": f"""
Generate curriculum content for: {standard_id}
Description: {description}

Required output format:
{{
  "assessment_boundaries": "* Bullet point 1\\n* Bullet point 2",
  "common_misconceptions": [
    "Misconception 1",
    "Misconception 2", 
    "Misconception 3"
  ]
}}

Guidelines:
- Assessment Boundaries: 1-3 bullet points (what IS/is NOT assessed)
- Common Misconceptions: 3-5 specific student errors
- Each bullet starts with "* "
- Be specific and actionable
""",
        "curriculum_path": str(get_curriculum_path()),
    }, indent=2))


if __name__ == "__main__":
    main()
