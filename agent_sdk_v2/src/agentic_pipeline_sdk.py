"""
ELA Question Generation using Claude Agent SDK

Correct Architecture (from docs):
- Skills are filesystem artifacts in .claude/skills/
- SDK discovers skills automatically via setting_sources
- Claude autonomously invokes skills when relevant
- No manual loading of SKILL.md into system prompts!

Usage:
    from agentic_pipeline_sdk import generate_one_agentic
    result = await generate_one_agentic(request)

Requirements:
    pip install claude-agent-sdk
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root (where .claude/skills/ lives)
ROOT = Path(__file__).resolve().parents[1]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def extract_json(text: str) -> str:
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


async def generate_one_agentic(
    request: dict,
    *,
    verbose: bool = False,
) -> dict:
    """
    Generate one ELA question using Claude Agent SDK.
    
    The SDK:
    - Points to project directory with .claude/skills/
    - Discovers skills automatically via setting_sources
    - Claude autonomously invokes skills when relevant
    - Uses Skill, Read, Write, Bash tools
    
    Args:
        request: Question generation request
        verbose: Enable detailed logging
    
    Returns:
        Generation result with question content
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {
            "success": False,
            "error": "claude_agent_sdk not installed. Install with: pip install claude-agent-sdk",
            "timestamp": utc_timestamp(),
            "generatedContent": {"generated_content": []},
        }
    
    # Build the prompt for the agent
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    substandard_description = skills.get("substandard_description", "")
    grade = request.get("grade", "3")
    qtype = request.get("type", "mcq")
    difficulty = request.get("difficulty", "medium")
    
    prompt = f"""Generate an ELA {qtype.upper()} question with the following requirements:

- Standard ID: {substandard_id}
- Standard Description: {substandard_description}
- Grade Level: {grade}
- Question Type: {qtype}
- Difficulty: {difficulty}

Return the question as a JSON object with "id" and "content" fields."""

    # Configure the agent SDK - skills are discovered automatically!
    options = ClaudeAgentOptions(
        cwd=str(ROOT),  # Project with .claude/skills/
        setting_sources=["user", "project"],  # Load Skills from filesystem
        allowed_tools=["Skill", "Read", "Write", "Bash"],  # Enable tools
    )
    
    if verbose:
        logger.info(f"Starting agent with cwd: {ROOT}")
        logger.info(f"Prompt: {prompt[:200]}...")
    
    try:
        result_content = None
        
        # Run the agent - it discovers and uses skills automatically!
        async for message in query(prompt=prompt, options=options):
            if verbose:
                logger.info(f"Agent message: {message}")
            
            # Capture the final result
            if hasattr(message, "content"):
                result_content = message.content
            elif isinstance(message, dict) and "content" in message:
                result_content = message["content"]
            elif isinstance(message, str):
                result_content = message
        
        if not result_content:
            return {
                "success": False,
                "error": "Agent returned no content",
                "timestamp": utc_timestamp(),
                "generatedContent": {"generated_content": []},
            }
        
        # Parse the result
        try:
            if isinstance(result_content, str):
                json_str = extract_json(result_content)
                parsed = json.loads(json_str)
            else:
                parsed = result_content
            
            # Normalize content
            content = parsed.get("content", {})
            content["image_url"] = []
            
            return {
                "success": True,
                "error": None,
                "timestamp": utc_timestamp(),
                "generatedContent": {
                    "generated_content": [{
                        "id": parsed.get("id", ""),
                        "content": content,
                        "request": request,
                    }]
                },
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Failed to parse agent response: {e}",
                "timestamp": utc_timestamp(),
                "generatedContent": {"generated_content": []},
                "raw_response": str(result_content)[:500],
            }
            
    except Exception as e:
        logger.exception("Agent SDK error")
        return {
            "success": False,
            "error": str(e),
            "timestamp": utc_timestamp(),
            "generatedContent": {"generated_content": []},
        }


async def list_available_skills(verbose: bool = False) -> list[str]:
    """
    List available skills discovered by the SDK.
    
    Returns list of skill names.
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return []
    
    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        setting_sources=["user", "project"],
        allowed_tools=["Skill"],
    )
    
    skills = []
    async for message in query(
        prompt="What Skills are available? List them briefly.",
        options=options
    ):
        if verbose:
            print(message)
        if isinstance(message, str):
            skills.append(message)
    
    return skills
