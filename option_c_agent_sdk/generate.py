"""
Agentic MCQ Generation using Claude Agent SDK.

This module provides the main generation function that uses
Claude in fully agentic mode with custom MCP tools.
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import query, ClaudeAgentOptions

from .tools import create_curriculum_mcp_server, TOOL_NAMES


def _utc_ts() -> str:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _extract_json(text: str) -> str:
    """Extract JSON object from text."""
    text = text.strip()
    if not text:
        return ""
    
    # Try to find JSON in code fence
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fence_match:
        return fence_match.group(1).strip()
    
    # Find first { and matching }
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
                return text[start:i+1]
    return text


async def generate_mcq_agentic(
    request: dict,
    *,
    timeout_seconds: int = 120,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Generate one MCQ using fully agentic approach.
    
    Claude autonomously calls lookup_curriculum and populate_curriculum
    tools to get context before generating the MCQ.
    
    Args:
        request: MCQ generation request with skills, difficulty, etc.
        timeout_seconds: Max time to wait for response
        verbose: Print progress messages
    
    Returns:
        Generation result with MCQ content
    """
    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "ANTHROPIC_API_KEY not set",
            "generation_mode": "agentic",
        }
    
    # Extract request details
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    substandard_description = skills.get("substandard_description", "")
    difficulty = request.get("difficulty", "easy")
    
    if verbose:
        print(f"  [AGENTIC] Generating MCQ for {substandard_id} ({difficulty})")
    
    # Build prompt - explicitly require tool usage
    prompt = f"""Generate a Grade 3 ELA multiple-choice question.

REQUEST:
{json.dumps(request, indent=2)}

REQUIRED STEPS:
1. FIRST: Call lookup_curriculum with substandard_id="{substandard_id}"
2. IF has_boundaries=False OR has_misconceptions=False: Call populate_curriculum
3. THEN: Generate an MCQ using the curriculum context

You MUST call lookup_curriculum before generating the MCQ.

OUTPUT FORMAT (JSON only, no markdown):
{{
  "id": "l_3_1_a_mcq_{difficulty}_001",
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
}}"""

    # Create MCP server
    if verbose:
        print(f"  [MCP] Creating server with tools: {TOOL_NAMES}")
    
    mcp_server = create_curriculum_mcp_server()
    
    # Configure options - THIS IS THE KEY FIX
    # Tools may need mcp__<server>__<tool> format
    mcp_tool_names = [f"mcp__curriculum__{name}" for name in TOOL_NAMES]
    
    if verbose:
        print(f"  [DEBUG] MCP tool names: {mcp_tool_names}")
    
    options = ClaudeAgentOptions(
        mcp_servers={"curriculum": mcp_server},  # Dict format
        allowed_tools=mcp_tool_names + TOOL_NAMES,  # Try both formats
        permission_mode="bypassPermissions",  # Allow all tools without prompting
    )
    
    if verbose:
        print(f"  [QUERY] Starting with allowed_tools={TOOL_NAMES}")
    
    # WORKAROUND: Convert string prompt to async generator
    # This fixes the "ProcessTransport is not ready for writing" bug
    # See: https://github.com/anthropics/claude-agent-sdk-python/issues/386
    async def prompt_generator():
        yield {
            "type": "user",
            "message": {"role": "user", "content": prompt},
            "parent_tool_use_id": None,
            "session_id": "default",
        }
    
    # Consume messages with timeout
    result_text = ""
    tools_used = []
    message_count = 0
    
    try:
        async with asyncio.timeout(timeout_seconds):
            async for message in query(prompt=prompt_generator(), options=options):
                message_count += 1
                
                # Log all messages for debugging
                msg_type = type(message).__name__
                if verbose:
                    print(f"  [MSG {message_count}] type={msg_type}")
                
                # Track tool usage
                if hasattr(message, "tool_use"):
                    tool_use = message.tool_use
                    tool_name = getattr(tool_use, "name", "unknown")
                    tool_input = getattr(tool_use, "input", {})
                    tools_used.append({"name": tool_name, "input": tool_input})
                    if verbose:
                        print(f"  [TOOL CALL] Claude -> {tool_name}")
                
                # Capture result
                if hasattr(message, "result"):
                    result_text = str(message.result)
                    if verbose:
                        print(f"      -> result: {result_text[:100]}...")
                elif hasattr(message, "text"):
                    result_text += str(message.text)
                    if verbose:
                        print(f"      -> text: {message.text[:100] if message.text else '(empty)'}...")
                elif hasattr(message, "content"):
                    content = message.content
                    if isinstance(content, str):
                        result_text += content
                        if verbose:
                            print(f"      -> content(str): {content[:100]}...")
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                result_text += block.get("text", "")
                        if verbose and content:
                            print(f"      -> content(list): {len(content)} blocks")
    
    except TimeoutError:
        if verbose:
            print(f"  [TIMEOUT] {timeout_seconds}s elapsed (messages={message_count})")
        return {
            "success": False,
            "error": f"Timeout after {timeout_seconds}s",
            "generation_mode": "agentic",
            "messages_received": message_count,
            "tools_used": tools_used,
        }
    except Exception as e:
        import traceback
        if verbose:
            print(f"  [ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "generation_mode": "agentic",
        }
    
    if verbose:
        print(f"  [DONE] Processed {message_count} messages, tools: {[t['name'] for t in tools_used]}")
    
    # Parse result
    if not result_text:
        return {
            "success": False,
            "error": "No result text received",
            "generation_mode": "agentic",
            "messages_received": message_count,
            "tools_used": tools_used,
        }
    
    try:
        json_str = _extract_json(result_text)
        parsed = json.loads(json_str)
        
        if verbose:
            print(f"  [SUCCESS] MCQ generated")
        
        return {
            "success": True,
            "error": None,
            "timestamp": _utc_ts(),
            "generation_mode": "agentic",
            "tools_used": tools_used,
            "generatedContent": {
                "generated_content": [{
                    "id": parsed.get("id", ""),
                    "content": parsed.get("content", {}),
                    "request": request,
                }]
            },
        }
    except json.JSONDecodeError as e:
        if verbose:
            print(f"  [JSON ERROR] {e}")
        return {
            "success": False,
            "error": f"JSON parse error: {e}",
            "generation_mode": "agentic",
            "raw_result": result_text[:500],
        }
