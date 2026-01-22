"""
Grade 3 ELA MCQ generation pipeline.

Supports:
- Skills API mode: container with CCAPI_ELA_MCQ_SKILL_ID, code_execution tool.
- Fallback: skill file as system prompt, standard messages.create.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from . import config
from .formatters import normalize_content, parsed_to_item

logger = logging.getLogger(__name__)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _extract_json(text: str) -> str:
    """Take first JSON object from text, optionally inside ```json ... ```.
    
    Looks for JSON with "id" and "content" keys (our expected shape).
    Tries: code fences first, then plain JSON object.
    """
    text = text.strip()
    if not text:
        return ""
    
    # Try code fence first (```json ... ``` or ``` ... ```)
    # Find the code fence, then extract balanced JSON inside
    fence_match = re.search(r"```(?:json)?\s*(\{)", text, re.MULTILINE)
    if fence_match:
        start_pos = fence_match.end(1) - 1  # Position of opening {
        # Find matching closing } by counting braces
        depth = 0
        for i in range(start_pos, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start_pos:i+1].strip()
                    # Quick validation: should have "id" and "content"
                    if '"id"' in candidate and '"content"' in candidate:
                        return candidate
                    break
    
    # Try to find JSON object with "id" and "content" anywhere in text
    # Look for { ... "id" ... "content" ... }
    pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*"id"[\s\S]*?"content"[\s\S]*?\}'
    m = re.search(pattern, text)
    if m:
        candidate = m.group(0)
        # Validate it's balanced braces
        if candidate.count("{") == candidate.count("}"):
            return candidate
    
    # Fallback: find first {...} (original logic)
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


def _get_text_from_message_content(content: list) -> str:
    """Extract combined text from Message content blocks.
    
    Handles: text blocks, tool_result blocks (for code_execution), and tool_use blocks.
    For Skills API with code_execution, text may be in tool_result.content.
    Prioritizes the LAST text block (often contains the final answer).
    """
    parts = []
    for block in content or []:
        t = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if t == "text":
            txt = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
            if txt:
                parts.append(txt)
        elif t == "tool_result" or t in ("text_editor_code_execution_tool_result", "bash_code_execution_tool_result"):
            # For code_execution: tool_result may contain text in content
            # When Claude writes files via code_execution, the JSON might be in stdout/stderr
            result_content = getattr(block, "content", None) or (block.get("content") if isinstance(block, dict) else None)
            if isinstance(result_content, list):
                # Extract text from nested content blocks (text, text_delta, etc.)
                for nested in result_content:
                    nt = getattr(nested, "type", None) or (nested.get("type") if isinstance(nested, dict) else None)
                    if nt in ("text", "text_delta"):
                        nested_txt = getattr(nested, "text", None) or (nested.get("text") if isinstance(nested, dict) else "")
                        if nested_txt:
                            parts.append(nested_txt)
            elif isinstance(result_content, str):
                parts.append(result_content)
        # tool_use blocks don't have extractable text, skip them
    
    # For Skills API with code_execution, Claude often puts the final answer in the LAST text block
    # If we have multiple parts, prefer the last one (it's usually the final output)
    if len(parts) > 1:
        # Return all parts joined, but the last one is most important
        return "\n".join(parts)
    elif parts:
        return parts[0]
    return ""


async def generate_one(request: dict, *, skill_id: str | None = None, model: str | None = None) -> dict:
    """
    Generate one ELA MCQ.

    request: { "type":"mcq", "grade","skills", "subject","curriculum","difficulty" }
    skill_id: override; default from config CCAPI_ELA_MCQ_SKILL_ID.
    model: override; default from config CCAPI_LLM_MODEL.

    Returns:
        {
          "error": None | str,
          "success": bool,
          "timestamp": "ISO8601Z",
          "generatedContent": { "generated_content": [ { "id", "content", "request" } ] }
        }
    """
    model = model or config.CCAPI_LLM_MODEL
    sid = skill_id or config.CCAPI_ELA_MCQ_SKILL_ID
    use_skills_api = bool(sid and config.ANTHROPIC_API_KEY)
    generation_mode = "skills_api" if use_skills_api else "fallback"

    if not config.ANTHROPIC_API_KEY:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "unknown",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "error": "anthropic package not installed",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "unknown",
        }

    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    # For Skills API: explicitly request JSON in response, not in a file
    user_content = f"""Generate the MCQ question for this request. Return the JSON directly in your response (not in a file).

{json.dumps(request, indent=2)}"""

    if use_skills_api:
        # Skills API: container + code_execution tool
        # Explicit user message requests JSON directly (not in a file)
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
        # If still empty, check stop_reason and log for debugging
        if not raw:
            stop_reason = getattr(resp, "stop_reason", None)
            logger.warning(f"Empty response from Skills API. stop_reason={stop_reason}, content_blocks={len(resp.content) if resp.content else 0}")
            # Log block types for debugging
            if resp.content:
                block_types = [getattr(b, "type", None) or (b.get("type") if isinstance(b, dict) else None) for b in resp.content]
                logger.debug(f"Content block types: {block_types}")
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
        system = (
            "You are executing a Claude Code Skill. Follow the instructions in the skill definition exactly.\n\n"
            + skill_content
            + "\n\nGenerate your response following the skill's output schema. Respond with ONLY the JSON object, no markdown or extra text."
        )
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": f"Execute the skill with this input:\n\n{user_content}"}],
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
        # resp.content is list of ContentBlock
        raw = _get_text_from_message_content(resp.content) if hasattr(resp.content, "__iter__") else ""
        if not raw and hasattr(resp, "content"):
            # Classic Messages API: content can be a list of blocks
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
