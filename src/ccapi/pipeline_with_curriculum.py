"""
Grade 3 ELA MCQ generation pipeline with curriculum context.

This pipeline:
1. Python orchestrates curriculum lookup/population
2. Uses curriculum context in prompt
3. Supports Skills API (preferred) or skill files (fallback)

This is the "normal way" - Python controls the workflow, not Claude.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .curriculum_lookup import lookup_curriculum
from .populate_curriculum import populate_curriculum_entry
from .formatters import normalize_content, parsed_to_item
from .pipeline import _utc_ts, _extract_json, _get_text_from_message_content

logger = logging.getLogger(__name__)


async def generate_one_with_curriculum(
    request: dict,
    *,
    curriculum_path: Path | None = None,
    skill_id: str | None = None,
    model: str | None = None,
) -> dict:
    """
    Generate one ELA MCQ with curriculum context.
    
    Python orchestrates:
    1. Curriculum lookup/population
    2. Skills API or skill file loading
    3. Prompt building with curriculum context
    
    Args:
        request: {
            "type": "mcq",
            "grade": "3",
            "skills": {
                "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
                "substandard_description": "..."
            },
            "subject": "ela",
            "curriculum": "common core",
            "difficulty": "easy"
        }
        curriculum_path: Path to curriculum.md (default: option_c_agent_sdk/data/curriculum.md)
        skill_id: Override skill ID (default from config)
        model: Override model (default from config)
    
    Returns:
        {
            "error": None | str,
            "success": bool,
            "timestamp": "ISO8601Z",
            "generatedContent": { "generated_content": [ { "id", "content", "request" } ] },
            "generation_mode": "skills_api_with_curriculum" | "fallback_with_curriculum"
        }
    """
    model = model or config.CCAPI_LLM_MODEL
    sid = skill_id or config.CCAPI_ELA_MCQ_SKILL_ID
    use_skills_api = bool(sid and config.ANTHROPIC_API_KEY)
    generation_mode = "skills_api_with_curriculum" if use_skills_api else "fallback_with_curriculum"
    
    if not config.ANTHROPIC_API_KEY:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": generation_mode,
        }
    
    try:
        import anthropic
    except ImportError:
        return {
            "error": "anthropic package not installed",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": generation_mode,
        }
    
    # Get substandard_id from request
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    
    # STEP 1: Check if curriculum data exists, populate if missing
    if curriculum_path is None:
        # Default to option_c_agent_sdk/data/curriculum.md
        root = Path(__file__).resolve().parents[2]  # Go up to ccapi/
        curriculum_path = root / "data" / "curriculum.md"
    
    populate_result = await populate_curriculum_entry(
        substandard_id,
        curriculum_path,
        force_regenerate=False,
    )
    
    # STEP 2: Lookup curriculum (now it should have data)
    curriculum_info = lookup_curriculum(substandard_id, curriculum_path)
    
    # STEP 3: Build prompt with curriculum context
    base_user_content = f"""Generate the MCQ question for this request. Return the JSON directly in your response (not in a file).

{json.dumps(request, indent=2)}"""
    
    # Add curriculum context to user message
    user_content = base_user_content
    if curriculum_info.get("found"):
        boundaries = curriculum_info.get('assessment_boundaries', 'Not specified')
        misconceptions = curriculum_info.get('common_misconceptions', [])
        
        curriculum_context = f"""

CURRICULUM CONTEXT (from curriculum.md for substandard_id: {substandard_id}):"""
        
        if boundaries and boundaries != 'Not specified':
            curriculum_context += f"""
- Assessment Boundaries: {boundaries}"""
        
        if misconceptions:
            curriculum_context += f"""
- Common Misconceptions:
{chr(10).join([f"  * {m}" for m in misconceptions])}"""
        
        curriculum_context += """

Use this context to:
1. Ensure your question aligns with the assessment boundaries
2. Create distractors that reflect the common misconceptions listed above"""
        
        user_content = base_user_content + curriculum_context
    
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    
    if use_skills_api:
        # Skills API: container + code_execution tool
        try:
            resp = await client.beta.messages.create(
                model=model,
                max_tokens=4096,
                betas=["code-execution-2025-08-25", "skills-2025-10-02"],
                container={
                    "skills": [{"type": "custom", "skill_id": sid, "version": "latest"}],
                },
                messages=[{"role": "user", "content": user_content}],
                tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
            )
        except Exception as e:
            logger.exception("Skills API request failed")
            return {
                "error": str(e),
                "success": False,
                "timestamp": _utc_ts(),
                "generatedContent": {"generated_content": []},
                "generation_mode": generation_mode,
            }
        raw = _get_text_from_message_content(resp.content)
        if not raw:
            stop_reason = getattr(resp, "stop_reason", None)
            logger.warning(f"Empty response from Skills API. stop_reason={stop_reason}")
    else:
        # Fallback: skill as system prompt
        try:
            skill_path = config.SKILL_PATH
            skill_content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
        except Exception as e:
            return {
                "error": f"Failed to load skill: {e}",
                "success": False,
                "timestamp": _utc_ts(),
                "generatedContent": {"generated_content": []},
                "generation_mode": generation_mode,
            }
        
        # Add curriculum context to system prompt for fallback mode
        system_base = (
            "You are executing a Claude Code Skill. Follow the instructions in the skill definition exactly.\n\n"
            + skill_content
        )
        
        if curriculum_info.get("found"):
            boundaries = curriculum_info.get('assessment_boundaries', 'Not specified')
            misconceptions = curriculum_info.get('common_misconceptions', [])
            
            curriculum_instruction = "\n\nCURRICULUM CONTEXT:\n"
            if boundaries and boundaries != 'Not specified':
                curriculum_instruction += f"Assessment Boundaries: {boundaries}\n"
            if misconceptions:
                curriculum_instruction += f"Common Misconceptions:\n{chr(10).join([f'  * {m}' for m in misconceptions])}\n"
            curriculum_instruction += "\nUse the assessment boundaries to ensure your question stays within scope, and use the common misconceptions to create effective distractors."
            
            system_base += curriculum_instruction
        
        system = system_base + "\n\nGenerate your response following the skill's output schema. Respond with ONLY the JSON object, no markdown or extra text."
        
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": f"Execute the skill with this input:\n\n{base_user_content}"}],
            )
        except Exception as e:
            logger.exception("Messages create failed")
            return {
                "error": str(e),
                "success": False,
                "timestamp": _utc_ts(),
                "generatedContent": {"generated_content": []},
                "generation_mode": generation_mode,
            }
        raw = _get_text_from_message_content(resp.content) if hasattr(resp.content, "__iter__") else ""
        if not raw and hasattr(resp, "content"):
            for b in (resp.content or []):
                if getattr(b, "type", None) == "text":
                    raw = getattr(b, "text", "") or ""
                    break
    
    if not raw:
        return {
            "error": "Empty model response",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": generation_mode,
        }
    
    js = _extract_json(raw)
    try:
        parsed = json.loads(js)
    except json.JSONDecodeError as e:
        return {
            "error": f"Invalid JSON: {e}",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": generation_mode,
        }
    
    item = parsed_to_item(parsed, request)
    return {
        "error": None,
        "success": True,
        "timestamp": _utc_ts(),
        "generatedContent": {"generated_content": [item]},
        "generation_mode": generation_mode,
    }
