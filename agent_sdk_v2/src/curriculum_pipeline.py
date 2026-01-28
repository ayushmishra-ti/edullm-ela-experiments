"""
Curriculum Population Pipeline - Separate from Question Generation

Architecture:
- SKILL.md is the SINGLE SOURCE OF TRUTH
- Sub-agent reads populate-curriculum/SKILL.md
- Generates learning objectives, assessment boundaries, misconceptions
- Saves to curriculum.md file

This is a PRE-GENERATION step. Run this before batch question generation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root
ROOT = Path(__file__).resolve().parents[1]


def _utc_ts() -> str:
    """RFC3339 UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _load_skill(skill_name: str) -> str:
    """Load a SKILL.md file by name."""
    skill_path = ROOT / ".claude" / "skills" / skill_name / "SKILL.md"
    if skill_path.exists():
        try:
            return skill_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_name}: {e}")
    return ""


def _get_curriculum_path() -> Path:
    """Get the curriculum.md file path."""
    # Check for reference folder first
    ref_path = ROOT / ".claude" / "skills" / "ela-question-generation" / "reference" / "curriculum.md"
    if ref_path.exists():
        return ref_path
    
    # Fall back to data folder
    data_path = ROOT / "data" / "curriculum.md"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    return data_path


def _extract_json(text: str) -> str:
    """Extract first JSON object from text."""
    text = text.strip()
    if not text:
        return ""
    
    # Try code fence first
    fence_match = re.search(r"```(?:json)?\s*(\{)", text, re.MULTILINE)
    if fence_match:
        start_pos = fence_match.end(1) - 1
        depth = 0
        for i in range(start_pos, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start_pos:i+1].strip()
    
    # Fallback: find first {...}
    start = text.find("{")
    if start < 0:
        return text
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text


def _extract_text_from_response(response) -> str:
    """Extract text from Anthropic SDK response."""
    try:
        content = getattr(response, "content", None) or []
        out = ""
        for block in content:
            if hasattr(block, "text"):
                out += block.text
        return out.strip()
    except Exception:
        return ""


def _check_curriculum_exists(standard_id: str) -> dict | None:
    """Check if curriculum data already exists for a standard."""
    curriculum_path = _get_curriculum_path()
    if not curriculum_path.exists():
        return None
    
    try:
        content = curriculum_path.read_text(encoding="utf-8")
        
        # Look for the standard in the file
        if f"Standard ID: {standard_id}" not in content:
            return None
        
        # Check if it has actual data (not just placeholders)
        # Split by --- and find the section for this standard
        sections = content.split("---")
        for section in sections:
            if f"Standard ID: {standard_id}" in section:
                has_objectives = "Learning Objectives:" in section and "*None specified*" not in section.split("Learning Objectives:")[1].split("Assessment Boundaries:")[0]
                has_boundaries = "Assessment Boundaries:" in section and "*None specified*" not in section.split("Assessment Boundaries:")[1].split("Common Misconceptions:")[0]
                has_misconceptions = "Common Misconceptions:" in section and "*None specified*" not in section.split("Common Misconceptions:")[1].split("Difficulty Definitions:")[0] if "Difficulty Definitions:" in section else True
                
                if has_objectives and has_boundaries:
                    return {
                        "exists": True,
                        "has_objectives": has_objectives,
                        "has_boundaries": has_boundaries,
                        "has_misconceptions": has_misconceptions,
                    }
        
        return None
    except Exception:
        return None


def _save_curriculum_data(standard_id: str, data: dict) -> bool:
    """Save curriculum data to curriculum.md file."""
    curriculum_path = _get_curriculum_path()
    
    learning_objectives = data.get("learning_objectives", [])
    assessment_boundaries = data.get("assessment_boundaries", [])
    common_misconceptions = data.get("common_misconceptions", [])
    
    # Format as bullet points
    if isinstance(learning_objectives, list):
        objectives_text = "\n".join([f"* {obj}" for obj in learning_objectives])
    else:
        objectives_text = str(learning_objectives)
    
    if isinstance(assessment_boundaries, list):
        boundaries_text = "\n".join([f"* {b}" for b in assessment_boundaries])
    else:
        boundaries_text = str(assessment_boundaries)
    
    if isinstance(common_misconceptions, list):
        misconceptions_text = "\n".join([f"* {m}" for m in common_misconceptions])
    else:
        misconceptions_text = str(common_misconceptions)
    
    try:
        if curriculum_path.exists():
            content = curriculum_path.read_text(encoding="utf-8")
            
            # Check if standard already exists
            if f"Standard ID: {standard_id}" in content:
                # Update existing entry
                sections = content.split("---")
                updated = False
                
                for i, section in enumerate(sections):
                    if f"Standard ID: {standard_id}" in section:
                        # Update learning objectives
                        section = re.sub(
                            r"(Learning Objectives:\s*)(?:\*None specified\*|.*?)(?=\n\nAssessment Boundaries:)",
                            f"\\1{objectives_text}\n",
                            section,
                            flags=re.DOTALL
                        )
                        # Update assessment boundaries
                        section = re.sub(
                            r"(Assessment Boundaries:\s*)(?:\*None specified\*|.*?)(?=\n\nCommon Misconceptions:)",
                            f"\\1{boundaries_text}\n",
                            section,
                            flags=re.DOTALL
                        )
                        # Update common misconceptions
                        section = re.sub(
                            r"(Common Misconceptions:\s*)(?:\*None specified\*|.*?)(?=\n\nDifficulty Definitions:|\n---|\Z)",
                            f"\\1{misconceptions_text}\n",
                            section,
                            flags=re.DOTALL
                        )
                        sections[i] = section
                        updated = True
                        break
                
                if updated:
                    content = "---".join(sections)
                    curriculum_path.write_text(content, encoding="utf-8")
                    return True
            
            # Standard doesn't exist, append new entry
            new_entry = f"""

---

## {standard_id}

Standard ID: {standard_id}

Learning Objectives:
{objectives_text}

Assessment Boundaries:
{boundaries_text}

Common Misconceptions:
{misconceptions_text}

Difficulty Definitions:
* Easy: Recall single concept
* Medium: Apply rule or compare
* Hard: Multiple concepts or subtle distinctions
"""
            content += new_entry
            curriculum_path.write_text(content, encoding="utf-8")
            return True
        else:
            # Create new file
            new_content = f"""# ELA Curriculum Data

This file contains learning objectives, assessment boundaries, and common misconceptions for ELA standards.
Generated by the populate-curriculum skill.

---

## {standard_id}

Standard ID: {standard_id}

Learning Objectives:
{objectives_text}

Assessment Boundaries:
{boundaries_text}

Common Misconceptions:
{misconceptions_text}

Difficulty Definitions:
* Easy: Recall single concept
* Medium: Apply rule or compare
* Hard: Multiple concepts or subtle distinctions
"""
            curriculum_path.write_text(new_content, encoding="utf-8")
            return True
            
    except Exception as e:
        logger.error(f"Failed to save curriculum data: {e}")
        return False


async def populate_curriculum_for_standard(
    standard_id: str,
    standard_description: str,
    grade: str = "3",
    *,
    model: str | None = None,
    force: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Populate curriculum data for a single standard using sub-agent.
    
    Architecture:
    - Sub-agent reads populate-curriculum/SKILL.md
    - Claude (sub-agent) generates curriculum data following SKILL.md
    - Data is saved to curriculum.md
    
    Args:
        standard_id: The standard ID (e.g., "CCSS.ELA-LITERACY.L.3.1.A")
        standard_description: Description of the standard
        grade: Grade level
        model: Optional model override
        force: Force regeneration even if data exists
        verbose: Enable verbose logging
    
    Returns:
        Result with generated curriculum data
    """
    try:
        import anthropic
    except ImportError:
        return {
            "success": False,
            "error": "anthropic package not installed",
            "standard_id": standard_id,
        }
    
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return {
            "success": False,
            "error": "ANTHROPIC_API_KEY not set",
            "standard_id": standard_id,
        }
    
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    
    # Check if data already exists
    if not force:
        existing = _check_curriculum_exists(standard_id)
        if existing and existing.get("exists"):
            return {
                "success": True,
                "source": "existing",
                "standard_id": standard_id,
                "message": "Curriculum data already exists",
            }
    
    # Load the skill as system prompt for sub-agent
    skill_content = _load_skill("populate-curriculum")
    if not skill_content:
        return {
            "success": False,
            "error": "populate-curriculum SKILL.md not found",
            "standard_id": standard_id,
        }
    
    # Spawn sub-agent: Claude reads SKILL.md and generates curriculum data
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        
        # Minimal request - SKILL.md has all the instructions
        subagent_request = {
            "standard_id": standard_id,
            "standard_description": standard_description,
            "grade": grade,
        }
        
        if verbose:
            logger.info(f"Spawning sub-agent for curriculum: {standard_id}")
        
        response = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=skill_content,  # Sub-agent reads SKILL.md
            messages=[{
                "role": "user",
                "content": f"Generate curriculum data for this standard:\n\n{json.dumps(subagent_request, indent=2)}"
            }],
        )
        
        response_text = _extract_text_from_response(response)
        if not response_text:
            return {
                "success": False,
                "error": "Sub-agent returned no content",
                "standard_id": standard_id,
            }
        
        # Parse JSON from response
        json_str = _extract_json(response_text)
        try:
            curriculum_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Failed to parse curriculum JSON: {e}",
                "standard_id": standard_id,
                "raw_response": response_text[:500],
            }
        
        if verbose:
            logger.info(f"Sub-agent generated curriculum for: {standard_id}")
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "standard_id": standard_id,
        }
    
    # Save to curriculum.md
    saved = _save_curriculum_data(standard_id, curriculum_data)
    
    return {
        "success": True,
        "source": "generated_by_subagent",
        "standard_id": standard_id,
        "curriculum_data": curriculum_data,
        "saved_to_file": saved,
        "timestamp": _utc_ts(),
    }


async def populate_curriculum_batch(
    standards: list[dict],
    *,
    model: str | None = None,
    force: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Populate curriculum data for multiple standards.
    
    Args:
        standards: List of {"standard_id": "...", "standard_description": "...", "grade": "..."}
        model: Optional model override
        force: Force regeneration even if data exists
        verbose: Enable verbose logging
    
    Returns:
        Batch result with stats
    """
    results = []
    stats = {
        "total": len(standards),
        "success": 0,
        "skipped_existing": 0,
        "failed": 0,
    }
    
    for i, std in enumerate(standards):
        standard_id = std.get("standard_id", "")
        standard_description = std.get("standard_description", "")
        grade = std.get("grade", "3")
        
        if verbose:
            logger.info(f"[{i+1}/{len(standards)}] Processing: {standard_id}")
        
        result = await populate_curriculum_for_standard(
            standard_id,
            standard_description,
            grade,
            model=model,
            force=force,
            verbose=verbose,
        )
        
        results.append(result)
        
        if result.get("success"):
            if result.get("source") == "existing":
                stats["skipped_existing"] += 1
            else:
                stats["success"] += 1
        else:
            stats["failed"] += 1
    
    return {
        "results": results,
        "stats": stats,
        "timestamp": _utc_ts(),
    }
