#!/usr/bin/env python3
"""
Populate Curriculum Script for Agent Skills.

Usage:
    python scripts/populate_curriculum.py "<standard_id>" "<standard_description>"

Example:
    python scripts/populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A" "Explain the function of nouns..."

Generates assessment boundaries and common misconceptions, saves to curriculum.md.
"""

import json
import os
import re
import sys
from pathlib import Path


def get_curriculum_path() -> Path:
    """Find curriculum.md file."""
    script_dir = Path(__file__).parent.parent
    possible_paths = [
        script_dir / "references" / "curriculum.md",
        script_dir.parent.parent.parent / "data" / "curriculum.md",
        Path.cwd() / "data" / "curriculum.md",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return possible_paths[1]  # Default to data/curriculum.md


def generate_curriculum_prompt(standard_id: str, standard_description: str) -> str:
    """Generate prompt for Claude to create curriculum content."""
    return f"""Generate Assessment Boundaries and Common Misconceptions for this ELA standard:

Standard ID: {standard_id}
Standard Description: {standard_description}

Generate:

1. **Assessment Boundaries**: 1-3 concise bullet points specifying what IS and is NOT assessed.
   - Each bullet starts with "* " (asterisk + space)
   - Keep each bullet to 1-2 sentences max
   - Focus on grade-appropriate scope

2. **Common Misconceptions**: 3-5 bullet points of typical student errors.
   - Each bullet starts with "* " (asterisk + space)
   - One specific misconception per bullet
   - Useful for creating MCQ distractors

Return ONLY a JSON object:
{{
  "assessment_boundaries": "* Assessment is limited to...\\n* Students should...",
  "common_misconceptions": [
    "Students may confuse...",
    "Students often think...",
    "Students might incorrectly believe..."
  ]
}}"""


def update_curriculum_file(
    curriculum_path: Path,
    standard_id: str,
    assessment_boundaries: str,
    common_misconceptions: list,
) -> bool:
    """Update curriculum.md with new data."""
    if not curriculum_path.exists():
        return False
    
    try:
        content = curriculum_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading curriculum file: {e}", file=sys.stderr)
        return False
    
    # Split by "---" to get entries
    parts = content.split("---")
    updated = False
    
    for i, entry in enumerate(parts):
        if f"Standard ID: {standard_id}" in entry:
            original_entry = entry
            
            # Update Assessment Boundaries
            if assessment_boundaries:
                ab_pattern = r"(Assessment Boundaries:\s*)(?:\*None specified\*|.*?)(?=\n\nCommon Misconceptions:)"
                boundaries_text = assessment_boundaries.strip()
                replacement = f"\\1{boundaries_text}\n"
                entry = re.sub(ab_pattern, replacement, entry, flags=re.DOTALL)
            
            # Update Common Misconceptions
            if common_misconceptions:
                misconceptions_text = "\n".join([f"* {m.strip()}" for m in common_misconceptions if m.strip()])
                cm_pattern = r"(Common Misconceptions:\s*)(?:\*None specified\*|.*?)(?=\n\nDifficulty Definitions:)"
                replacement = f"\\1{misconceptions_text}\n"
                entry = re.sub(cm_pattern, replacement, entry, flags=re.DOTALL)
            
            if entry != original_entry:
                parts[i] = entry
                updated = True
                break
    
    if updated:
        new_content = "---".join(parts)
        try:
            curriculum_path.write_text(new_content, encoding="utf-8")
            return True
        except Exception as e:
            print(f"Error writing curriculum file: {e}", file=sys.stderr)
            return False
    
    return False


def main():
    if len(sys.argv) < 3:
        print(json.dumps({
            "error": "Usage: python populate_curriculum.py <standard_id> <standard_description>",
            "example": 'python populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A" "Explain the function of nouns..."'
        }, indent=2))
        sys.exit(1)
    
    standard_id = sys.argv[1]
    standard_description = sys.argv[2]
    
    # Generate the prompt for Claude
    prompt = generate_curriculum_prompt(standard_id, standard_description)
    
    # Output the prompt for Claude to process
    # When Claude runs this script, it should:
    # 1. See this prompt
    # 2. Generate the JSON response
    # 3. Parse and save to curriculum.md
    
    result = {
        "action": "populate_curriculum",
        "standard_id": standard_id,
        "standard_description": standard_description,
        "prompt": prompt,
        "instructions": """
To complete this action:
1. Generate assessment boundaries and common misconceptions based on the prompt above
2. Return JSON with 'assessment_boundaries' (string with bullet points) and 'common_misconceptions' (array of strings)
3. The curriculum.md file will be updated with this content

Example response format:
{
  "assessment_boundaries": "* Assessment is limited to identifying basic parts of speech.\\n* Complex sentences are out of scope.",
  "common_misconceptions": [
    "Students may confuse adjectives with adverbs",
    "Students often think verbs only show physical action"
  ]
}
""",
        "curriculum_path": str(get_curriculum_path()),
    }
    
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
