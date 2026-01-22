"""
Populate curriculum.md with Assessment Boundaries and Common Misconceptions.

This module provides functions to:
1. Generate Assessment Boundaries and Common Misconceptions for a standard
2. Update curriculum.md with the generated data
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


async def generate_curriculum_content(
    standard_id: str,
    standard_description: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Generate Assessment Boundaries and Common Misconceptions for a standard.
    
    This function uses Claude Agent SDK to generate:
    - Assessment Boundaries: What should and shouldn't be assessed
    - Common Misconceptions: Typical student errors for this standard
    
    Args:
        standard_id: The standard ID (e.g., "CCSS.ELA-LITERACY.L.3.1.A")
        standard_description: The standard description
        model: Optional model override
    
    Returns:
        {
            "assessment_boundaries": str,
            "common_misconceptions": list[str]
        }
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        raise ImportError("claude-agent-sdk not installed. Install with: pip install claude-agent-sdk")
    
    prompt = f"""Generate Assessment Boundaries and Common Misconceptions for this Grade 3 ELA standard:

Standard ID: {standard_id}
Standard Description: {standard_description}

Generate:

1. **Assessment Boundaries**: 1-3 concise bullet points specifying what IS and is NOT assessed.
   - Each bullet starts with "* " (asterisk + space)
   - Combine what IS assessed and what is NOT in concise statements
   - Keep each bullet to 1-2 sentences max
   - Focus on Grade 3 appropriate scope

2. **Common Misconceptions**: 3-5 bullet points of typical student errors.
   - Each bullet starts with "* " (asterisk + space)
   - One specific misconception per bullet
   - Useful for creating MCQ distractors

IMPORTANT: Use bullet format with "* " prefix, NOT paragraph format.

Return ONLY a JSON object in this format:
{{
  "assessment_boundaries": "* Assessment is limited to [specific scope]. [What is NOT assessed].\\n* [Another boundary point if needed].",
  "common_misconceptions": [
    "Students may confuse...",
    "Students often think...",
    "Students might incorrectly believe..."
  ]
}}

Example assessment_boundaries format:
"* Assessment is limited to identifying basic parts of speech in simple sentences. Complex sentence structures are out of scope.\\n* Students should explain functions in general terms. Technical terminology beyond the five basic parts of speech is not assessed."

No markdown, no code fences, just the JSON object."""

    try:
        result_text = ""
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Bash"],
                setting_sources=["project"],  # Load skills from filesystem
            ),
        ):
            if hasattr(message, "result"):
                result_text += str(message.result)
        
        # Extract JSON from response
        import json
        import re
        
        # Try to find JSON object
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"assessment_boundaries"[\s\S]*?"common_misconceptions"[\s\S]*?\}', result_text)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return {
                "assessment_boundaries": parsed.get("assessment_boundaries", ""),
                "common_misconceptions": parsed.get("common_misconceptions", []),
            }
        
        # Fallback: try to parse entire response as JSON
        try:
            parsed = json.loads(result_text.strip())
            return {
                "assessment_boundaries": parsed.get("assessment_boundaries", ""),
                "common_misconceptions": parsed.get("common_misconceptions", []),
            }
        except json.JSONDecodeError:
            pass
        
        # If JSON extraction failed, return error
        return {
            "assessment_boundaries": None,
            "common_misconceptions": None,
            "error": "Failed to extract JSON from response",
        }
        
    except Exception as e:
        return {
            "assessment_boundaries": None,
            "common_misconceptions": None,
            "error": str(e),
        }


async def populate_curriculum_entry(
    standard_id: str,
    curriculum_path: Path,
    *,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """
    Populate a curriculum entry with Assessment Boundaries and Common Misconceptions.
    
    If the entry already has this data and force_regenerate=False, returns existing data.
    Otherwise, generates new content and updates curriculum.md.
    
    Args:
        standard_id: The standard ID to populate
        curriculum_path: Path to curriculum.md
        force_regenerate: If True, regenerate even if data exists
    
    Returns:
        {
            "success": bool,
            "assessment_boundaries": str | None,
            "common_misconceptions": list[str] | None,
            "updated": bool  # Whether curriculum.md was updated
        }
    """
    from .curriculum_lookup import lookup_curriculum
    
    # Default curriculum path if not provided
    if curriculum_path is None:
        curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    # Check if data already exists
    existing = lookup_curriculum(standard_id, curriculum_path)
    
    if existing.get("found"):
        has_boundaries = bool(existing.get("assessment_boundaries"))
        has_misconceptions = bool(existing.get("common_misconceptions"))
        
        # If both exist and not forcing regenerate, return existing
        if has_boundaries and has_misconceptions and not force_regenerate:
            return {
                "success": True,
                "assessment_boundaries": existing.get("assessment_boundaries"),
                "common_misconceptions": existing.get("common_misconceptions"),
                "updated": False,
            }
        
        # Need to generate
        standard_description = existing.get("standard_description", "")
        
        # Generate content (this will call Claude via Agent SDK)
        generated = await generate_curriculum_content(
            standard_id,
            standard_description,
        )
        
        if generated.get("error"):
            return {
                "success": False,
                "assessment_boundaries": None,
                "common_misconceptions": None,
                "updated": False,
                "error": generated.get("error"),
            }
        
        # Update curriculum.md
        updated = update_curriculum_file(
            curriculum_path,
            standard_id,
            generated.get("assessment_boundaries"),
            generated.get("common_misconceptions"),
        )
        
        return {
            "success": True,
            "assessment_boundaries": generated.get("assessment_boundaries"),
            "common_misconceptions": generated.get("common_misconceptions"),
            "updated": updated,
        }
    
    return {
        "success": False,
        "assessment_boundaries": None,
        "common_misconceptions": None,
        "updated": False,
        "error": f"Standard {standard_id} not found in curriculum",
    }


def update_curriculum_file(
    curriculum_path: Path,
    standard_id: str,
    assessment_boundaries: str | None,
    common_misconceptions: list[str] | None,
) -> bool:
    """
    Update curriculum.md file with new Assessment Boundaries and Common Misconceptions.
    
    Args:
        curriculum_path: Path to curriculum.md
        standard_id: The standard ID to update
        assessment_boundaries: New assessment boundaries text (can be multi-line)
        common_misconceptions: List of misconception strings
    
    Returns:
        True if file was updated, False otherwise
    """
    if not curriculum_path.exists():
        return False
    
    try:
        content = curriculum_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading curriculum file: {e}")
        return False
    
    # Split by "---" to get entries (keep the separator)
    parts = content.split("---")
    updated = False
    
    for i, entry in enumerate(parts):
        # Check if this entry matches the standard_id
        if f"Standard ID: {standard_id}" in entry:
            original_entry = entry
            
            # Update Assessment Boundaries
            if assessment_boundaries:
                # Pattern: Assessment Boundaries: followed by optional content, then Common Misconceptions
                # Replace "*None specified*" or any existing content
                ab_pattern = r"(Assessment Boundaries:\s*)(?:\*None specified\*|.*?)(?=\n\nCommon Misconceptions:)"
                # Format boundaries - if it's a single string, use it; if it has newlines, preserve them
                boundaries_text = assessment_boundaries.strip()
                if not boundaries_text.startswith("*"):
                    # If not already formatted as bullets, add as plain text
                    boundaries_text = boundaries_text
                
                replacement = f"\\1{boundaries_text}\n"
                entry = re.sub(ab_pattern, replacement, entry, flags=re.DOTALL)
            
            # Update Common Misconceptions
            if common_misconceptions:
                # Format misconceptions as bullet points
                misconceptions_text = "\n".join([f"* {m.strip()}" for m in common_misconceptions if m.strip()])
                # Pattern: Common Misconceptions: followed by optional content, then Difficulty Definitions
                cm_pattern = r"(Common Misconceptions:\s*)(?:\*None specified\*|.*?)(?=\n\nDifficulty Definitions:)"
                replacement = f"\\1{misconceptions_text}\n"
                entry = re.sub(cm_pattern, replacement, entry, flags=re.DOTALL)
            
            if entry != original_entry:
                parts[i] = entry
                updated = True
                break
    
    if updated:
        # Rejoin entries with "---" separator
        new_content = "---".join(parts)
        try:
            curriculum_path.write_text(new_content, encoding="utf-8")
            return True
        except Exception as e:
            print(f"Error writing curriculum file: {e}")
            return False
    
    return False
