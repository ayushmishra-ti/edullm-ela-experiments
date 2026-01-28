"""
ELA Question Generation using Claude Agent SDK (Skills Approach)

Key points from the official docs:
- Skills are filesystem artifacts in .claude/skills/
- SDK discovers skills automatically via setting_sources
- Claude autonomously invokes skills when relevant
- NO manual loading of SKILL.md files!

The prompt flows:
1. User calls POST /generate with request data
2. main.py calls generate_one_agentic(request)
3. This module builds a prompt string from the request
4. Prompt is sent to SDK via query(prompt=..., options=...)
5. SDK discovers skills and Claude decides which to use

Reference: https://platform.claude.com/docs/en/agent-sdk/skills
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
    """RFC3339 UTC timestamp."""
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


def _extract_text_from_content(content) -> str:
    """Extract text from SDK message content."""
    if isinstance(content, str):
        return content
    
    text = ""
    try:
        if hasattr(content, "__iter__"):
            for block in content:
                if hasattr(block, "text"):
                    text += block.text
                elif isinstance(block, dict) and "text" in block:
                    text += block["text"]
        elif hasattr(content, "text"):
            text = content.text
    except Exception:
        text = str(content)
    
    return text.strip()


async def generate_one_agentic(
    request: dict,
    *,
    verbose: bool = False,
) -> dict:
    """
    Generate one ELA question using Claude Agent SDK with Skills.
    
    How the prompt flows:
    1. This function receives a request dict from main.py
    2. We build a prompt string from the request data
    3. We call query(prompt=..., options=...) - THIS IS WHERE PROMPT IS SENT
    4. SDK discovers skills from .claude/skills/
    5. Claude reads skill descriptions and decides which to invoke
    6. Claude generates the question following SKILL.md instructions
    
    Args:
        request: Question generation request with:
            - skills.substandard_id: e.g., "CCSS.ELA-LITERACY.L.3.1.A"
            - skills.substandard_description: Description of the standard
            - grade: Grade level (e.g., "3")
            - type: Question type ("mcq", "msq", "fill-in")
            - difficulty: "easy", "medium", "hard"
        verbose: Enable detailed logging
    
    Returns:
        Generation result with question content
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {
            "success": False,
            "error": "claude_agent_sdk not installed. Run: pip install claude-agent-sdk",
            "timestamp": utc_timestamp(),
            "generatedContent": {"generated_content": []},
        }
    
    # =========================================================================
    # STEP 1: Extract request data
    # =========================================================================
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    substandard_description = skills.get("substandard_description", "")
    grade = request.get("grade", "3")
    qtype = request.get("type", "mcq")
    difficulty = request.get("difficulty", "medium")
    
    # =========================================================================
    # STEP 2: Build the prompt
    # This is what gets sent to the SDK via query(prompt=...)
    # Claude will see this prompt and decide which skill to use
    # =========================================================================
    prompt = f"""Generate an ELA {qtype.upper()} question with the following requirements:

- Standard ID: {substandard_id}
- Standard Description: {substandard_description}
- Grade Level: {grade}
- Question Type: {qtype}
- Difficulty: {difficulty}

Return the question as a JSON object with "id" and "content" fields."""

    # =========================================================================
    # STEP 3: Configure SDK options
    # - cwd: Directory containing .claude/skills/
    # - setting_sources: REQUIRED to load skills from filesystem
    # - allowed_tools: Must include "Skill" to enable skill invocation
    # =========================================================================
    options = ClaudeAgentOptions(
        cwd=str(ROOT),                          # Project with .claude/skills/
        setting_sources=["user", "project"],    # REQUIRED: Load skills from filesystem
        allowed_tools=["Skill", "Read"],  # Skill: invoke skills, Read: read files
    )
    
    if verbose:
        logger.info(f"[SDK] Starting agent")
        logger.info(f"[SDK] cwd: {ROOT}")
        logger.info(f"[SDK] Standard: {substandard_id}")
        logger.info(f"[SDK] Type: {qtype}, Difficulty: {difficulty}")
        logger.info(f"[SDK] Prompt: {prompt[:100]}...")
    
    # =========================================================================
    # STEP 4: Send prompt to SDK via query()
    # This is where the prompt actually gets sent!
    # The SDK will:
    # - Discover skills in .claude/skills/
    # - Pass them to Claude
    # - Claude decides which skill matches the prompt
    # - Claude invokes the skill and generates the response
    # =========================================================================
    try:
        result_content = None
        session_id = None
        
        # query() is an async generator that yields messages
        # The prompt goes here ↓
        async for message in query(prompt=prompt, options=options):
            # Capture session ID for potential resume
            if hasattr(message, "session_id"):
                session_id = message.session_id
            
            if verbose:
                # Log what Claude is doing
                if hasattr(message, "content"):
                    content = message.content
                    if hasattr(content, "__iter__"):
                        for block in content:
                            if hasattr(block, "type"):
                                if block.type == "tool_use" and getattr(block, "name", "") == "Skill":
                                    skill_input = getattr(block, "input", {})
                                    logger.info(f"[SDK] Claude invoking skill: {skill_input}")
                                elif block.type == "text":
                                    text = getattr(block, "text", "")
                                    if text:
                                        logger.debug(f"[SDK] Claude: {text[:100]}...")
            
            # Capture the final result
            if hasattr(message, "result"):
                result_content = message.result
            elif hasattr(message, "content"):
                result_content = message.content
            elif isinstance(message, str):
                result_content = message
        
        if verbose:
            logger.info(f"[SDK] Agent completed")
        
        if not result_content:
            return {
                "success": False,
                "error": "Agent returned no content",
                "timestamp": utc_timestamp(),
                "generatedContent": {"generated_content": []},
            }
        
        # =====================================================================
        # STEP 5: Parse the response
        # Claude should return JSON following SKILL.md format
        # =====================================================================
        try:
            # Extract text from response
            text = _extract_text_from_content(result_content)
            json_str = extract_json(text) if text else ""
            
            if not json_str:
                return {
                    "success": False,
                    "error": "No JSON found in response",
                    "timestamp": utc_timestamp(),
                    "generatedContent": {"generated_content": []},
                    "raw_response": text[:500] if text else str(result_content)[:500],
                }
            
            parsed = json.loads(json_str)
            
            # Normalize content
            content = parsed.get("content", {})
            content["image_url"] = []
            
            return {
                "success": True,
                "error": None,
                "timestamp": utc_timestamp(),
                "session_id": session_id,
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
                "raw_response": text[:500] if text else str(result_content)[:500],
            }
            
    except Exception as e:
        logger.exception("[SDK] Agent error")
        return {
            "success": False,
            "error": str(e),
            "timestamp": utc_timestamp(),
            "generatedContent": {"generated_content": []},
        }


async def list_available_skills() -> list[dict]:
    """
    List available skills discovered by the SDK.
    
    This sends a prompt asking Claude to list skills.
    The SDK will discover skills and Claude will enumerate them.
    
    Returns:
        List with skill info
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return [{"error": "claude_agent_sdk not installed"}]
    
    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        setting_sources=["user", "project"],
        allowed_tools=["Skill"],
    )
    
    result = None
    # Prompt asking Claude to list skills
    async for message in query(
        prompt="What Skills are available? List each skill with its name and description.",
        options=options
    ):
        if hasattr(message, "result"):
            result = message.result
        elif isinstance(message, str):
            result = message
    
    return [{"response": result}] if result else []


async def generate_with_explicit_skill(
    request: dict,
    skill_name: str = "ela-question-generation",
    *,
    verbose: bool = False,
) -> dict:
    """
    Generate question explicitly invoking a skill by name.
    
    Use this when you want to GUARANTEE a specific skill is used,
    rather than letting Claude decide based on the description.
    
    The key difference is the prompt explicitly says "Use the X skill..."
    
    Args:
        request: Question generation request
        skill_name: Name of the skill to invoke
        verbose: Enable detailed logging
    
    Returns:
        Generation result
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {
            "success": False,
            "error": "claude_agent_sdk not installed",
        }
    
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    substandard_description = skills.get("substandard_description", "")
    grade = request.get("grade", "3")
    qtype = request.get("type", "mcq")
    difficulty = request.get("difficulty", "medium")
    
    # EXPLICIT skill invocation - mention skill by name in prompt
    prompt = f"""Use the {skill_name} skill to generate an ELA {qtype.upper()} question:

- Standard ID: {substandard_id}
- Standard Description: {substandard_description}
- Grade Level: {grade}
- Question Type: {qtype}
- Difficulty: {difficulty}

Return the question as a JSON object."""

    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        setting_sources=["user", "project"],
        allowed_tools=["Skill", "Read"],
    )
    
    if verbose:
        logger.info(f"[SDK] Explicitly invoking skill: {skill_name}")
    
    result = None
    async for message in query(prompt=prompt, options=options):
        if hasattr(message, "result"):
            result = message.result
        elif hasattr(message, "content"):
            result = message.content
    
    if not result:
        return {"success": False, "error": "No result"}
    
    try:
        text = _extract_text_from_content(result)
        json_str = extract_json(text)
        parsed = json.loads(json_str)
        
        content = parsed.get("content", {})
        content["image_url"] = []
        
        return {
            "success": True,
            "timestamp": utc_timestamp(),
            "generatedContent": {
                "generated_content": [{
                    "id": parsed.get("id", ""),
                    "content": content,
                    "request": request,
                }]
            },
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "raw": _extract_text_from_content(result)[:500],
        }
