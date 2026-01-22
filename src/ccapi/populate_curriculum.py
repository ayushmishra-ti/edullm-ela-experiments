"""
Populate curriculum.md with Assessment Boundaries and Common Misconceptions.

This module provides functions to:
1. Generate Assessment Boundaries and Common Misconceptions for a standard
2. Update curriculum.md with the generated data

Uses standard Anthropic API (not Agent SDK) for compatibility with parent folder.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from . import config
from .curriculum_lookup import lookup_curriculum

logger = logging.getLogger(__name__)


async def generate_curriculum_content(
    standard_id: str,
    standard_description: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Generate Assessment Boundaries and Common Misconceptions for a standard.
    
    This function uses standard Anthropic API to generate:
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
    if not config.ANTHROPIC_API_KEY:
        return {
            "assessment_boundaries": None,
            "common_misconceptions": None,
            "error": "ANTHROPIC_API_KEY not set",
        }
    
    try:
        import anthropic
    except ImportError:
        return {
            "assessment_boundaries": None,
            "common_misconceptions": None,
            "error": "anthropic package not installed",
        }
    
    model = model or config.CCAPI_LLM_MODEL
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    
    # Try Skills API first, fallback to skill file
    skill_id = config.CCAPI_POPULATE_CURRICULUM_SKILL_ID
    use_skills_api = bool(skill_id and config.ANTHROPIC_API_KEY)
    
    user_content = json.dumps({
        "standard_id": standard_id,
        "standard_description": standard_description,
        "force_regenerate": False
    }, indent=2)
    
    result_text = ""
    
    if use_skills_api:
        # Skills API: container + code_execution tool
        try:
            response = await client.beta.messages.create(
                model=model,
                max_tokens=4096,
                betas=["code-execution-2025-08-25", "skills-2025-10-02"],
                container={
                    "skills": [{"type": "custom", "skill_id": skill_id, "version": "latest"}],
                },
                messages=[{"role": "user", "content": f"Execute the skill with this input:\n\n{user_content}"}],
                tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
            )
            # Extract text from response (handles code_execution tool results)
            from .pipeline import _get_text_from_message_content
            result_text = _get_text_from_message_content(response.content)
        except Exception as e:
            # Fallback to skill file if Skills API fails
            use_skills_api = False
    
    if not use_skills_api:
        # Fallback: skill as system prompt
        try:
            skill_path = config.POPULATE_CURRICULUM_SKILL_PATH
            skill_content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
        except Exception as e:
            return {
                "assessment_boundaries": None,
                "common_misconceptions": None,
                "error": f"Failed to load skill: {e}",
            }
        
        system = (
            "You are executing a Claude Code Skill. Follow the instructions in the skill definition exactly.\n\n"
            + skill_content
            + "\n\nGenerate your response following the skill's output schema. Respond with ONLY the JSON object, no markdown or extra text."
        )
        
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": f"Execute the skill with this input:\n\n{user_content}"}],
            )
            
            # Extract text from response
            if hasattr(response, "content"):
                for block in response.content:
                    if hasattr(block, "text"):
                        result_text += block.text
        except Exception as e:
            return {
                "assessment_boundaries": None,
                "common_misconceptions": None,
                "error": f"Messages create failed: {e}",
            }
    
    if not result_text:
        return {
            "assessment_boundaries": None,
            "common_misconceptions": None,
            "error": "Empty response from API",
        }
    
    # Try to find JSON object with better error handling
    json_match = re.search(
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"assessment_boundaries"[\s\S]*?"common_misconceptions"[\s\S]*?\}',
        result_text
    )
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            return {
                "assessment_boundaries": parsed.get("assessment_boundaries", ""),
                "common_misconceptions": parsed.get("common_misconceptions", []),
            }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from regex match: {e}")
            logger.debug(f"Matched text: {json_match.group(0)[:200]}...")
    
    # Fallback: try to parse entire response as JSON
    try:
        parsed = json.loads(result_text.strip())
        return {
            "assessment_boundaries": parsed.get("assessment_boundaries", ""),
            "common_misconceptions": parsed.get("common_misconceptions", []),
        }
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse entire response as JSON: {e}")
        logger.debug(f"Response text (first 500 chars): {result_text[:500]}")
        pass
    
    # If JSON extraction failed, return error
    return {
        "assessment_boundaries": None,
        "common_misconceptions": None,
        "error": "Failed to extract JSON from response",
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
        
        # Generate content (this will call Claude via standard API)
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
