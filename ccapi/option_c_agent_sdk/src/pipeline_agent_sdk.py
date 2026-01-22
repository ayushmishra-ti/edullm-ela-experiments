"""
Grade 3 ELA MCQ generation pipeline using Claude Agent SDK.

DEPRECATED: This module is deprecated. The functionality has been moved to:
- Parent folder (ccapi/): `src/ccapi/pipeline_with_curriculum.py` - Python-orchestrated with curriculum context + skills
- This folder (option_c_agent_sdk/): `src/agentic_pipeline.py` - Fully agentic (Claude decides tool usage)

This file is kept for reference but should not be used in new code.
Use `generate_one_with_curriculum()` in parent folder or `generate_one_agentic()` in this folder instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .curriculum_lookup import lookup_curriculum

logger = logging.getLogger(__name__)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _extract_json(text: str) -> str:
    """Extract first JSON object from text, optionally inside ```json ... ```."""
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
                    candidate = text[start_pos:i+1].strip()
                    if '"id"' in candidate and '"content"' in candidate:
                        return candidate
                    break
    
    # Try to find JSON object with "id" and "content"
    pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"id"[\s\S]*?"content"[\s\S]*?\}'
    m = re.search(pattern, text)
    if m:
        candidate = m.group(0)
        if candidate.count("{") == candidate.count("}"):
            return candidate
    
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


def _normalize_content(content: dict) -> dict:
    """Ensure content has image_url=[] and answer_options as [{"key","text"}], etc."""
    out = dict(content)
    out["image_url"] = []
    opts = out.get("answer_options")
    if isinstance(opts, dict):
        out["answer_options"] = [{"key": k, "text": v} for k, v in opts.items()]
    elif isinstance(opts, list) and opts and isinstance(opts[0], dict):
        out["answer_options"] = [
            {"key": str(o.get("key", "")), "text": str(o.get("text", ""))} for o in opts
        ]
    return out


def _parsed_to_item(parsed: dict, request: dict, normalize: bool = True) -> dict:
    """
    Build standardized item from parsed LLM JSON and original request.
    
    parsed: { "id", "content": { "answer", "question", "image_url", "answer_options", ... } }
    """
    c = parsed.get("content", {})
    content = _normalize_content(c) if normalize else dict(c)
    return {
        "id": parsed.get("id", ""),
        "content": content,
        "request": request,
    }


async def generate_one_agent_sdk(
    request: dict,
    *,
    curriculum_path: Path | None = None,
    model: str | None = None,
) -> dict:
    """
    Generate one ELA MCQ using Claude Agent SDK with curriculum lookup tool.
    
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
        curriculum_path: Path to curriculum.md file
        model: Override model (default from config)
    
    Returns:
        {
            "error": None | str,
            "success": bool,
            "timestamp": "ISO8601Z",
            "generatedContent": { "generated_content": [ { "id", "content", "request" } ] },
            "generation_mode": "agent_sdk"
        }
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {
            "error": "claude-agent-sdk not installed. Install with: pip install claude-agent-sdk",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agent_sdk",
        }
    
    import os
    from anthropic import Anthropic
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agent_sdk",
        }
    
    # Get substandard_id from request
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    
    # STEP 1: Check if curriculum data exists, populate if missing
    from .populate_curriculum import populate_curriculum_entry
    
    # Default curriculum path if not provided
    if curriculum_path is None:
        # Go up from src/ to option_c_agent_sdk/, then to data/
        curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    populate_result = await populate_curriculum_entry(
        substandard_id,
        curriculum_path,
        force_regenerate=False,
    )
    
    # STEP 2: Lookup curriculum (now it should have data)
    curriculum_info = lookup_curriculum(substandard_id, curriculum_path)
    
    # Build the prompt
    prompt = f"""Generate a Grade 3 ELA multiple-choice question based on this request:

{json.dumps(request, indent=2)}

Curriculum context has been looked up for substandard_id: {substandard_id}

Use the assessment boundaries to ensure your question stays within scope, and use the common misconceptions to create effective distractors that reflect common student errors.

Return ONLY a valid JSON object matching this schema:
{{
  "id": "l_3_1_a_mcq_easy_001",
  "content": {{
    "answer": "B",
    "question": "...",
    "image_url": [],
    "answer_options": [
      {{"key": "A", "text": "..."}},
      {{"key": "B", "text": "..."}},
      {{"key": "C", "text": "..."}},
      {{"key": "D", "text": "..."}}
    ],
    "additional_details": "",
    "answer_explanation": "..."
  }}
}}

No markdown, no code fences, just the JSON object."""

    try:
        # Use Agent SDK with custom tool
        # Note: The Agent SDK uses a different pattern - we need to define tools properly
        # For now, let's use a simpler approach: pre-lookup and inject into prompt
        
        # Use the populated curriculum info
        if curriculum_info.get("found"):
            boundaries = curriculum_info.get('assessment_boundaries', 'Not specified')
            misconceptions = curriculum_info.get('common_misconceptions', [])
            
            if boundaries and boundaries != 'Not specified':
                prompt += f"""

CURRICULUM CONTEXT (from curriculum.md):
- Assessment Boundaries: {boundaries}
"""
            
            if misconceptions:
                prompt += f"""
- Common Misconceptions:
{chr(10).join([f"  * {m}" for m in misconceptions])}

Use this context to:
1. Ensure your question aligns with the assessment boundaries
2. Create distractors that reflect the common misconceptions listed above
"""
        
        # Use Agent SDK query
        # Note: We're using the SDK's query function which handles tool execution
        # For custom tools, we might need to use a different approach
        # Let's use the standard query for now and enhance later
        
        # Use Agent SDK with filesystem-based skills
        # The skill definition in skills/ela-mcq-generation/SKILL.md will be loaded
        # if setting_sources includes "project"
        result_item = None
        parse_error = None
        
        # Create the query generator
        query_gen = query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Bash"],  # Built-in tools for curriculum lookup
                setting_sources=["project"],  # Load skills from filesystem
            ),
        )
        
        # CRITICAL: Consume the entire generator without breaking early
        # Breaking from the loop causes cleanup in a different task context,
        # which triggers the "cancel scope" error. By consuming all messages,
        # cleanup happens in the same task context where the generator was created.
        async for message in query_gen:
            if hasattr(message, "result"):
                result_text = message.result
                # Extract JSON from result
                js = _extract_json(result_text)
                try:
                    parsed = json.loads(js)
                    # Convert to our format using local helper
                    # Store the result but DON'T break - continue consuming all messages
                    result_item = _parsed_to_item(parsed, request)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from Agent SDK response: {e}")
                    logger.debug(f"Response text: {result_text[:500]}")
                    parse_error = str(e)
                    # Continue consuming messages - don't break
        
        # Generator is now fully consumed and will close cleanly in the same task context
        
        # Return after loop completes (allows proper async cleanup)
        if result_item is not None:
            return {
                "error": None,
                "success": True,
                "timestamp": _utc_ts(),
                "generatedContent": {"generated_content": [result_item]},
                "generation_mode": "agent_sdk",
            }
        
        # If we get here, no valid JSON was found
        return {
            "error": parse_error or "No valid JSON found in Agent SDK response",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agent_sdk",
        }
        
    except Exception as e:
        logger.exception("Agent SDK request failed")
        return {
            "error": str(e),
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agent_sdk",
        }
