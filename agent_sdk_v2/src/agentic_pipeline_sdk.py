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

def _curriculum_md_path() -> Path:
    """
    Canonical curriculum file used by the question-generation skill.
    We update this locally before deployment.
    """
    return ROOT / ".claude" / "skills" / "ela-question-generation" / "reference" / "curriculum.md"


def lookup_curriculum(standard_id: str) -> str | None:
    """
    Extract curriculum data for a specific standard from curriculum.md.
    
    Instead of having Claude read the entire 8,190-line file,
    we pre-fetch only the relevant section (~30-40 lines).
    
    Args:
        standard_id: e.g., "CCSS.ELA-LITERACY.L.3.1.A"
    
    Returns:
        The curriculum block for that standard, or None if not found.
    """
    path = _curriculum_md_path()
    if not path.exists():
        logger.warning(f"curriculum.md not found at {path}")
        return None
    
    content = path.read_text(encoding="utf-8")
    
    # Split by block delimiter
    blocks = content.split("\n---\n")
    
    for block in blocks:
        # Check if this block contains the standard_id
        if f"Standard ID: {standard_id}" in block:
            return block.strip()
    
    logger.warning(f"Standard ID {standard_id} not found in curriculum.md")
    return None


def _format_bullets(items: object) -> str:
    if not items:
        return "*None specified*"
    if isinstance(items, list):
        cleaned = [str(x).strip() for x in items if str(x).strip()]
        return "\n".join([f"* {x}" for x in cleaned]) if cleaned else "*None specified*"
    # If skill ever returns a string, keep it
    s = str(items).strip()
    return s if s else "*None specified*"


def _update_curriculum_md_section(text: str, standard_id: str, data: dict) -> tuple[str, bool]:
    """
    Update the Learning Objectives / Assessment Boundaries / Common Misconceptions
    inside the existing curriculum.md section for a given Standard ID.

    Returns: (new_text, updated?)
    """
    if f"Standard ID: {standard_id}" not in text:
        return text, False

    # Find the block containing this standard (from Standard ID to next --- delimiter)
    block_re = re.compile(
        rf"(Standard ID:\s*{re.escape(standard_id)}[\s\S]*?)(?=\n---\n|\Z)",
        re.MULTILINE,
    )
    m = block_re.search(text)
    if not m:
        return text, False

    block = m.group(1)

    objectives = _format_bullets(data.get("learning_objectives"))
    boundaries = _format_bullets(data.get("assessment_boundaries"))
    misconceptions = _format_bullets(data.get("common_misconceptions"))

    def replace_section(block_text: str, header: str, next_header: str, new_body: str) -> str:
        # Replace anything between "Header:\n" and "\n\nNext Header:"
        pattern = re.compile(
            rf"({re.escape(header)}:\s*\n)([\s\S]*?)(\n\n{re.escape(next_header)}:)",
            re.MULTILINE,
        )
        if pattern.search(block_text):
            return pattern.sub(rf"\1{new_body}\3", block_text)
        return block_text

    block2 = block
    block2 = replace_section(block2, "Learning Objectives", "Assessment Boundaries", objectives)
    block2 = replace_section(block2, "Assessment Boundaries", "Common Misconceptions", boundaries)

    # Misconceptions section goes until Difficulty Definitions OR end of block
    mis_re = re.compile(
        r"(Common Misconceptions:\s*\n)([\s\S]*?)(\n\nDifficulty Definitions:)",
        re.MULTILINE,
    )
    if mis_re.search(block2):
        block2 = mis_re.sub(rf"\1{misconceptions}\3", block2)

    new_text = text[: m.start(1)] + block2 + text[m.end(1) :]
    return new_text, True


async def run_skill_return_json(
    *,
    skill_name: str,
    input_obj: dict,
    verbose: bool = False,
) -> dict:
    """
    Invoke a skill and parse the returned JSON object.

    This is for skills that return a JSON object NOT in the {id, content} question format
    (e.g., populate-curriculum).
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {"success": False, "error": "claude_agent_sdk not installed"}

    prompt = (
        f"Use the {skill_name} skill.\n\n"
        f"Input JSON:\n{json.dumps(input_obj, indent=2)}\n\n"
        "Return ONLY the JSON object."
    )

    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        setting_sources=["user", "project"],
        allowed_tools=["Skill", "Read"],
    )

    result_content = None
    async for message in query(prompt=prompt, options=options):
        if hasattr(message, "result"):
            result_content = message.result
        elif hasattr(message, "content"):
            result_content = message.content
        elif isinstance(message, str):
            result_content = message

    text = _extract_text_from_content(result_content) if result_content else ""
    json_str = extract_json(text) if text else ""
    if not json_str:
        return {"success": False, "error": "No JSON found in skill response", "raw_response": text[:500]}

    try:
        parsed = json.loads(json_str)
        if not isinstance(parsed, dict):
            return {"success": False, "error": "Skill returned non-object JSON", "raw_response": json_str[:500]}
        return {"success": True, "data": parsed}
    except Exception as e:
        return {"success": False, "error": str(e), "raw_response": json_str[:500]}


async def populate_curriculum_entry(
    *,
    standard_id: str,
    standard_description: str,
    grade: str = "3",
    verbose: bool = False,
) -> dict:
    """
    LOCAL-ONLY: Generate curriculum data using populate-curriculum skill and
    update curriculum.md in-place.
    """
    skill_result = await run_skill_return_json(
        skill_name="populate-curriculum",
        input_obj={
            "standard_id": standard_id,
            "standard_description": standard_description,
            "grade": grade,
        },
        verbose=verbose,
    )
    if not skill_result.get("success"):
        return {
            "success": False,
            "standard_id": standard_id,
            "error": skill_result.get("error", "Unknown error"),
            "raw_response": skill_result.get("raw_response"),
        }

    data = skill_result["data"]
    path = _curriculum_md_path()
    if not path.exists():
        return {
            "success": False,
            "standard_id": standard_id,
            "error": f"curriculum.md not found at {path}",
        }

    original = path.read_text(encoding="utf-8")
    updated_text, updated = _update_curriculum_md_section(original, standard_id, data)
    if not updated:
        return {
            "success": False,
            "standard_id": standard_id,
            "error": "Standard ID not found in curriculum.md (cannot update in-place).",
            "curriculum_path": str(path),
        }

    path.write_text(updated_text, encoding="utf-8")
    return {
        "success": True,
        "standard_id": standard_id,
        "curriculum_path": str(path),
        "updated": True,
        "curriculum_data": data,
    }


async def generate_one_agentic(
    request: dict,
    *,
    verbose: bool = False,
) -> dict:
    """
    Generate one ELA question using Claude Agent SDK with Skills.
    
    How the prompt flows:
    1. This function receives a request dict from main.py
    2. Pre-fetch curriculum data for the standard (~30 lines instead of 8,190)
    3. Build prompt with the pre-fetched curriculum context
    4. Call query(prompt=..., options=...) - THIS IS WHERE PROMPT IS SENT
    5. SDK discovers skills from .claude/skills/
    6. Claude reads skill descriptions and decides which to invoke
    7. Claude generates the question following SKILL.md instructions
    
    OPTIMIZATION: We pre-fetch curriculum data in Python before sending to SDK.
    This avoids Claude having to read the entire 8,190-line curriculum.md file,
    reducing context length from ~70K tokens to ~500 tokens.
    
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
    # STEP 2: Pre-fetch curriculum data (OPTIMIZATION)
    # Instead of having Claude read the entire 8,190-line curriculum.md,
    # we extract only the relevant ~30-40 lines for this standard.
    # This significantly reduces context length and cost.
    # =========================================================================
    curriculum_context = lookup_curriculum(substandard_id)
    
    if verbose:
        if curriculum_context:
            logger.info(f"[SDK] Pre-fetched curriculum data ({len(curriculum_context)} chars)")
        else:
            logger.info(f"[SDK] No curriculum data found for {substandard_id}")
    
    # =========================================================================
    # STEP 3: Build the prompt with pre-fetched curriculum
    # This is what gets sent to the SDK via query(prompt=...)
    # Claude will see this prompt and decide which skill to use
    # =========================================================================
    prompt = f"""Generate an ELA {qtype.upper()} question with the following requirements:

- Standard ID: {substandard_id}
- Standard Description: {substandard_description}
- Grade Level: {grade}
- Question Type: {qtype}
- Difficulty: {difficulty}
"""
    
    # Include pre-fetched curriculum data if available
    if curriculum_context:
        prompt += f"""
## Curriculum Context (Pre-fetched)
The following curriculum data is provided for your reference. Use this information
to create pedagogically aligned questions. DO NOT read curriculum.md - use this data:

{curriculum_context}
"""
    
    prompt += """
Return the question as a JSON object with "id" and "content" fields."""

    # =========================================================================
    # STEP 4: Configure SDK options
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
    # STEP 5: Send prompt to SDK via query()
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
        tool_calls = []  # Track all tool calls
        
        # query() is an async generator that yields messages
        # The prompt goes here ↓
        async for message in query(prompt=prompt, options=options):
            # Capture session ID for potential resume
            if hasattr(message, "session_id"):
                session_id = message.session_id
            
            if verbose:
                # Log message type
                msg_type = type(message).__name__
                logger.info(f"[SDK] Message type: {msg_type}")
                
                # Log all attributes for debugging
                if hasattr(message, "__dict__"):
                    for key in message.__dict__:
                        if key.startswith("_"):
                            continue
                        val = getattr(message, key, None)
                        if val is not None:
                            val_str = str(val)[:200] if len(str(val)) > 200 else str(val)
                            logger.info(f"[SDK]   {key}: {val_str}")
                
                # Log tool calls from content blocks
                if hasattr(message, "content"):
                    content = message.content
                    if hasattr(content, "__iter__"):
                        for block in content:
                            if hasattr(block, "type"):
                                block_type = getattr(block, "type", "")
                                
                                if block_type == "tool_use":
                                    tool_name = getattr(block, "name", "unknown")
                                    tool_id = getattr(block, "id", "")
                                    tool_input = getattr(block, "input", {})
                                    tool_calls.append({
                                        "tool": tool_name,
                                        "id": tool_id,
                                        "input": tool_input
                                    })
                                    logger.info(f"[SDK] ┌─ TOOL CALL: {tool_name}")
                                    logger.info(f"[SDK] │  ID: {tool_id}")
                                    logger.info(f"[SDK] │  Input: {json.dumps(tool_input, indent=2)[:300]}")
                                    logger.info(f"[SDK] └─────────────────────────")
                                    
                                elif block_type == "tool_result":
                                    tool_id = getattr(block, "tool_use_id", "")
                                    result = getattr(block, "content", "")
                                    result_str = str(result)[:300] if len(str(result)) > 300 else str(result)
                                    logger.info(f"[SDK] ┌─ TOOL RESULT (ID: {tool_id})")
                                    logger.info(f"[SDK] │  {result_str}")
                                    logger.info(f"[SDK] └─────────────────────────")
                                    
                                elif block_type == "text":
                                    text = getattr(block, "text", "")
                                    if text:
                                        text_preview = text[:150] + "..." if len(text) > 150 else text
                                        logger.info(f"[SDK] Claude text: {text_preview}")
            
            # Capture the final result
            if hasattr(message, "result"):
                result_content = message.result
            elif hasattr(message, "content"):
                result_content = message.content
            elif isinstance(message, str):
                result_content = message
        
        if verbose:
            logger.info(f"[SDK] Agent completed")
            logger.info(f"[SDK] Total tool calls: {len(tool_calls)}")
            for tc in tool_calls:
                logger.info(f"[SDK]   - {tc['tool']}")
        
        if not result_content:
            return {
                "success": False,
                "error": "Agent returned no content",
                "timestamp": utc_timestamp(),
                "generatedContent": {"generated_content": []},
            }
        
        # =====================================================================
        # STEP 6: Parse the response
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
    
    # Pre-fetch curriculum data (same optimization as generate_one_agentic)
    curriculum_context = lookup_curriculum(substandard_id)
    
    # EXPLICIT skill invocation - mention skill by name in prompt
    prompt = f"""Use the {skill_name} skill to generate an ELA {qtype.upper()} question:

- Standard ID: {substandard_id}
- Standard Description: {substandard_description}
- Grade Level: {grade}
- Question Type: {qtype}
- Difficulty: {difficulty}
"""
    
    if curriculum_context:
        prompt += f"""
## Curriculum Context (Pre-fetched)
{curriculum_context}
"""
    
    prompt += """
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
