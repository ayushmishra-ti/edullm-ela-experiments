#!/usr/bin/env python3
"""
Populate Curriculum Script for Agent Skills.

Usage:
    python scripts/populate_curriculum.py "<standard_id>" "<standard_description>"

Example:
    python scripts/populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A" "Explain the function of nouns..."

Generates learning objectives, assessment boundaries, and common misconceptions using Claude API, saves to curriculum.md.
"""

import json
import os
import re
import sys
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    ROOT = Path(__file__).resolve().parents[4]  # Go up to agent_sdk root
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass


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


def generate_curriculum_content(standard_id: str, standard_description: str) -> dict:
    """Call Claude API to generate curriculum content."""
    try:
        import anthropic
    except ImportError:
        return {"success": False, "error": "anthropic package not installed"}
    
    # NOTE: Cloud secrets sometimes include trailing newlines; strip whitespace
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY not set"}
    
    prompt = f"""Generate Learning Objectives, Assessment Boundaries, and Common Misconceptions for this ELA standard:

Standard ID: {standard_id}
Standard Description: {standard_description}

Generate:

1. **Learning Objectives**: 2-4 concise bullet points describing what a student should be able to do to demonstrate mastery of THIS standard description.
   - Each bullet starts with "* " (asterisk + space)
   - Use student-facing, measurable verbs (identify, explain, choose, revise, etc.)
   - MUST reflect the Standard Description; no drift to adjacent standards

2. **Assessment Boundaries**: 1-3 concise bullet points specifying what IS and is NOT assessed.
   - Each bullet starts with "* " (asterisk + space)
   - Keep each bullet to 1-2 sentences max
   - Focus on grade-appropriate scope

3. **Common Misconceptions**: 3-5 bullet points of typical student errors.
   - Each bullet starts with "* " (asterisk + space)
   - One specific misconception per bullet
   - These will be used to create effective MCQ distractors

Return ONLY a JSON object (no markdown fences):
{{
  "learning_objectives": "* Students can...\\n* Students can...",
  "assessment_boundaries": "* Assessment is limited to...\\n* Students should...",
  "common_misconceptions": [
    "Students may confuse...",
    "Students often think...",
    "Students might incorrectly believe..."
  ]
}}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        
        # Extract text from response
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        
        # Parse JSON from response
        # Try to find JSON object
        json_match = re.search(
            r'\{[\s\S]*"learning_objectives"[\s\S]*"assessment_boundaries"[\s\S]*"common_misconceptions"[\s\S]*\}',
            text,
        )
        if json_match:
            generated_data = json.loads(json_match.group(0))
        else:
            # Try parsing entire text
            generated_data = json.loads(text.strip())
        
        return {
            "success": True,
            "learning_objectives": generated_data.get("learning_objectives", ""),
            "assessment_boundaries": generated_data.get("assessment_boundaries", ""),
            "common_misconceptions": generated_data.get("common_misconceptions", []),
        }
        
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse JSON response: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_curriculum_file(
    curriculum_path: Path,
    standard_id: str,
    learning_objectives: str,
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

            # Update Learning Objectives
            if learning_objectives:
                lo_pattern = r"(Learning Objectives:\s*)(?:\*None specified\*|.*?)(?=\n\nAssessment Boundaries:)"
                objectives_text = learning_objectives.strip()
                replacement = f"\\1{objectives_text}\n"
                entry = re.sub(lo_pattern, replacement, entry, flags=re.DOTALL)
            
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
            "success": False,
            "error": "Usage: python populate_curriculum.py <standard_id> <standard_description>",
            "example": 'python populate_curriculum.py "CCSS.ELA-LITERACY.L.3.1.A" "Explain the function of nouns..."'
        }, indent=2))
        sys.exit(1)
    
    standard_id = sys.argv[1]
    standard_description = sys.argv[2]
    
    # Generate content using Claude API
    result = generate_curriculum_content(standard_id, standard_description)
    
    if not result.get("success"):
        print(json.dumps(result, indent=2))
        sys.exit(1)
    
    # Update curriculum.md
    curriculum_path = get_curriculum_path()
    file_updated = update_curriculum_file(
        curriculum_path,
        standard_id,
        result.get("learning_objectives", ""),
        result.get("assessment_boundaries", ""),
        result.get("common_misconceptions", []),
    )
    
    output = {
        "success": True,
        "standard_id": standard_id,
        "learning_objectives": result.get("learning_objectives"),
        "assessment_boundaries": result.get("assessment_boundaries"),
        "common_misconceptions": result.get("common_misconceptions"),
        "file_updated": file_updated,
        "curriculum_path": str(curriculum_path),
    }
    
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
