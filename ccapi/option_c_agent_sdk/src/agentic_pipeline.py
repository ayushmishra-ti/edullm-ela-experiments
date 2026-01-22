"""
Truly Agentic MCQ Generation Pipeline using Claude Agent SDK.

This pipeline lets Claude autonomously decide:
1. When to look up curriculum data
2. When to populate missing curriculum data
3. How to use the context to generate high-quality MCQs

Unlike the original pipeline that hardcodes the workflow in Python,
this implementation gives Claude full control over tool usage.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │  User Request: "Generate MCQ for CCSS.ELA-LITERACY.L.3.1.A"    │
    └─────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │  Claude thinks: "I need curriculum context"                     │
    │  Claude calls: lookup_curriculum(substandard_id)               │
    └─────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │  Tool returns data (or indicates missing data)                  │
    │  If missing: Claude calls populate_curriculum(...)              │
    └─────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │  Claude generates MCQ with curriculum context                   │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

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
    """Build standardized item from parsed LLM JSON and original request."""
    c = parsed.get("content", {})
    content = _normalize_content(c) if normalize else dict(c)
    return {
        "id": parsed.get("id", ""),
        "content": content,
        "request": request,
    }


# ============================================================================
# MCP Server Setup
# ============================================================================

def create_mcp_server_with_tools(curriculum_path: Path | None = None):
    """
    Create an in-process MCP server with curriculum tools.
    
    This allows Claude to call our custom tools (lookup_curriculum, populate_curriculum)
    during the agent loop.
    
    Args:
        curriculum_path: Path to curriculum.md (optional, uses default)
    
    Returns:
        MCP server instance
    """
    try:
        from claude_agent_sdk import create_sdk_mcp_server, tool
    except ImportError:
        raise ImportError(
            "claude-agent-sdk not installed. Install with: pip install claude-agent-sdk"
        )
    
    from .agentic_tools import tool_lookup_curriculum, tool_populate_curriculum
    
    # Default curriculum path
    if curriculum_path is None:
        curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    # Create tool wrappers that use the specific curriculum path
    @tool(
        "lookup_curriculum",
        """Look up curriculum information for a standard ID.
        
Returns assessment boundaries and common misconceptions from curriculum.md.
Use this FIRST before generating any MCQ to understand:
- What should and shouldn't be assessed (assessment boundaries)  
- Common student errors to use as distractors (misconceptions)

If the returned data shows has_boundaries=False or has_misconceptions=False,
you should call populate_curriculum to generate the missing data.""",
        {
            "substandard_id": str,  # The standard ID (e.g., 'CCSS.ELA-LITERACY.L.3.1.A')
        }
    )
    async def lookup_curriculum_tool(args: dict) -> dict:
        result = await tool_lookup_curriculum(
            args["substandard_id"],
            str(curriculum_path)
        )
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    
    @tool(
        "populate_curriculum",
        """Generate and save curriculum data for a standard.
        
Use this when lookup_curriculum returns missing data (has_boundaries=False or has_misconceptions=False).
This tool will:
1. Generate appropriate Assessment Boundaries for the standard
2. Generate Common Misconceptions (useful for MCQ distractors)
3. Save the data to curriculum.md for future reuse

After calling this, use lookup_curriculum again to get the populated data.""",
        {
            "substandard_id": str,
            "standard_description": str,
        }
    )
    async def populate_curriculum_tool(args: dict) -> dict:
        result = await tool_populate_curriculum(
            args["substandard_id"],
            args["standard_description"],
            str(curriculum_path)
        )
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
    
    # Create the MCP server
    server = create_sdk_mcp_server(
        name="curriculum-tools",
        version="1.0.0",
        tools=[lookup_curriculum_tool, populate_curriculum_tool]
    )
    
    return server


# ============================================================================
# Agentic Generation Function
# ============================================================================

async def generate_one_agentic(
    request: dict,
    *,
    curriculum_path: Path | None = None,
    model: str | None = None,
    verbose: bool = True,
) -> dict:
    """
    Generate one ELA MCQ using truly agentic approach.
    
    Claude autonomously decides when to:
    1. Look up curriculum data
    2. Populate missing curriculum data
    3. Generate the MCQ
    
    Args:
        request: MCQ generation request
        curriculum_path: Path to curriculum.md
        model: Optional model override
    
    Returns:
        Generation result with MCQ content
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {
            "error": "claude-agent-sdk not installed. Install with: pip install claude-agent-sdk",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
        }
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
        }
    
    # Default curriculum path
    if curriculum_path is None:
        curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    # Get substandard info from request
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    substandard_description = skills.get("substandard_description", "")
    difficulty = request.get("difficulty", "easy")
    
    # Build the prompt - Force tool usage to prevent deadlocks
    # NOTE: No pre-fetched curriculum data - Claude MUST use tools to get it
    prompt = f"""Generate a Grade 3 ELA multiple-choice question for this request:

{json.dumps(request, indent=2)}

MANDATORY WORKFLOW (YOU MUST FOLLOW THIS SEQUENCE):
1. FIRST: You MUST call lookup_curriculum tool with substandard_id: "{substandard_id}"
   - This is REQUIRED - do not skip this step
   - Wait for the tool result before proceeding

2. IF MISSING DATA: If the lookup returns has_boundaries=False or has_misconceptions=False:
   - You MUST call populate_curriculum tool with:
     - substandard_id: "{substandard_id}"
     - standard_description: "{substandard_description}"
   - Wait for the tool result
   - Then call lookup_curriculum again to get the populated data

3. FINALLY: Generate an MCQ that:
   - Stays within the assessment boundaries from the curriculum data
   - Uses common misconceptions to create effective distractors
   - Matches the difficulty level: {difficulty}

CRITICAL: Do not generate the MCQ until you have curriculum context from the tools.
Start by calling lookup_curriculum NOW.

Return ONLY a valid JSON object matching this schema:
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
}}

No markdown code fences in your final answer, just the JSON object."""

    try:
        # Create MCP server with our custom tools
        print(f"  🔧 Creating MCP server with curriculum tools...")
        try:
            mcp_server = create_mcp_server_with_tools(curriculum_path)
            print(f"  ✓ MCP server created successfully")
        except Exception as e:
            logger.exception(f"Failed to create MCP server: {e}")
            print(f"  ✗ Failed to create MCP server: {e}")
            raise
        
        # Log the start of agentic generation
        print(f"  🚀 Starting agentic generation for {substandard_id}...")
        print(f"  📋 Claude will autonomously decide which tools to call")
        
        # Use query() with MCP server - Claude will decide when to call tools
        result_text = ""
        result_item = None
        parse_error = None
        tools_used = []
        
        # Create query generator with custom MCP tools
        print(f"  📡 Creating query generator with MCP tools...")
        print(f"  ⏳ This may take a moment - Claude is processing your request...")
        try:
            # Try passing MCP server as a list (current approach)
            query_gen = query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    mcp_servers=[mcp_server],  # List of MCP servers
                    setting_sources=["project"],  # Load skills from SKILL.md files
                ),
            )
            print(f"  ✓ Query generator created, waiting for messages...")
        except TypeError as e:
            # If list doesn't work, try dict format
            if "mcp_servers" in str(e).lower() or "dict" in str(e).lower():
                logger.warning(f"MCP server list format failed, trying dict format: {e}")
                print(f"  🔄 Trying alternative MCP server format...")
                query_gen = query(
                    prompt=prompt,
                    options=ClaudeAgentOptions(
                        mcp_servers={"curriculum-tools": mcp_server},  # Dict format
                        setting_sources=["project"],
                    ),
                )
                print(f"  ✓ Query generator created (dict format), waiting for messages...")
            else:
                raise
        except Exception as e:
            logger.exception(f"Failed to create query generator: {e}")
            print(f"  ✗ Failed to create query generator: {e}")
            print(f"  💡 Error type: {type(e).__name__}")
            raise
        
        # Consume entire generator - Claude will call tools as needed
        # Add hard timeout to prevent infinite hangs
        message_count = 0
        timeout_seconds = 180  # 3 minutes max per generation
        
        try:
            print(f"  🔄 Starting to consume messages from Claude...")
            print(f"  ⏱️  Timeout: {timeout_seconds}s (will fail if Claude doesn't respond)")
            
            # Use asyncio.timeout for Python 3.11+, fallback for older versions
            try:
                # Python 3.11+ has asyncio.timeout
                async with asyncio.timeout(timeout_seconds):
                    async for message in query_gen:
                        message_count += 1
                        if verbose and message_count == 1:
                            print(f"  📨 Received first message (type: {type(message).__name__})")
                        
                        # Log message type for debugging (verbose mode)
                        if verbose:
                            msg_type = type(message).__name__
                            msg_attrs = [attr for attr in dir(message) if not attr.startswith("_")]
                            if not hasattr(generate_one_agentic, "_debug_printed"):
                                print(f"  🔍 Debug: Message type = {msg_type}, attributes = {msg_attrs[:10]}")
                                generate_one_agentic._debug_printed = True
                        
                        # Check for tool_use attribute
                        if hasattr(message, "tool_use"):
                            tool_use = message.tool_use
                            tool_name = getattr(tool_use, "name", None) or getattr(tool_use, "tool_name", "unknown")
                            tool_input = getattr(tool_use, "input", None) or getattr(tool_use, "args", {})
                            tool_id = getattr(tool_use, "id", None) or getattr(tool_use, "tool_call_id", None)
                            
                            tool_info = {"name": tool_name, "input": tool_input if isinstance(tool_input, dict) else {}, "id": tool_id}
                            tools_used.append(tool_info)
                            print(f"  🤖 Claude → Tool Call: {tool_name}")
                            if tool_input and isinstance(tool_input, dict):
                                args_str = ", ".join([f"{k}={str(v)[:50]}{'...' if len(str(v)) > 50 else ''}" for k, v in tool_input.items()])
                                if args_str:
                                    print(f"     Args: {args_str}")
                            logger.info(f"Claude called tool: {tool_name} with args: {tool_input}")
                        
                        # Check for tool results
                        if hasattr(message, "tool_result"):
                            tool_result = message.tool_result
                            tool_name = getattr(tool_result, "name", "unknown")
                            is_error = getattr(tool_result, "is_error", False)
                            result_content = getattr(tool_result, "content", None) or getattr(tool_result, "result", "")
                            if is_error:
                                print(f"  ⚠️  Tool Result: {tool_name} → ERROR: {str(result_content)[:100]}")
                            else:
                                result_preview = str(result_content)[:100] if result_content else ""
                                print(f"  ✓ Tool Result: {tool_name} → Success")
                                if result_preview:
                                    print(f"     Preview: {result_preview}...")
                            logger.info(f"Tool {tool_name} returned result (error={is_error})")
                        
                        # Capture the final text result
                        if hasattr(message, "result"):
                            result_text = str(message.result)
                        elif hasattr(message, "text"):
                            result_text += message.text
                        elif hasattr(message, "content"):
                            content = message.content
                            if isinstance(content, str):
                                result_text += content
                            elif isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        result_text += block.get("text", "")
            except TimeoutError:
                error_msg = f"Claude agent stalled: no messages emitted within {timeout_seconds}s"
                logger.error(error_msg)
                print(f"  ⚠️  {error_msg}")
                print(f"  💡 This usually means Claude is stuck in deliberation. Consider:")
                print(f"     - Making tool calls mandatory in the prompt")
                print(f"     - Using semi-agentic mode (pre-call tools in Python)")
                raise RuntimeError(error_msg)
        except RuntimeError:
            # Re-raise timeout errors
            raise
        except Exception as e:
            logger.exception(f"Error consuming query generator: {e}")
            print(f"  ✗ Error consuming messages: {e}")
            raise
        
        if message_count == 0:
            error_msg = "No messages received from query generator - it may have hung or failed silently"
            logger.error(error_msg)
            print(f"  ⚠️  {error_msg}")
            return {
                "error": error_msg,
                "success": False,
                "timestamp": _utc_ts(),
                "generatedContent": {"generated_content": []},
                "generation_mode": "agentic",
                "tools_used": tools_used,
            }
        
        print(f"  📊 Processed {message_count} messages from Claude")
        
        # Extract JSON from the final response
        if result_text:
            js = _extract_json(result_text)
            try:
                parsed = json.loads(js)
                result_item = _parsed_to_item(parsed, request)
                print(f"  ✓ MCQ generated successfully")
                if tools_used:
                    print(f"  📊 Tools used by Claude: {', '.join([t['name'] for t in tools_used])}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON: {e}")
                parse_error = str(e)
                print(f"  ✗ Failed to parse JSON response: {e}")
        
        if result_item:
            return {
                "error": None,
                "success": True,
                "timestamp": _utc_ts(),
                "generatedContent": {"generated_content": [result_item]},
                "generation_mode": "agentic",
                "tools_used": tools_used,  # Track what Claude decided to use
            }
        
        return {
            "error": parse_error or "No valid JSON found in response",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
            "tools_used": tools_used,
        }
        
    except Exception as e:
        logger.exception("Agentic generation failed")
        error_msg = str(e)
        print(f"  ✗ Agentic generation failed: {error_msg}")
        return {
            "error": error_msg,
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
        }


# ============================================================================
# Alternative: Simpler Agentic Approach using query() with Read/Bash tools
# ============================================================================

async def generate_one_agentic_simple(
    request: dict,
    *,
    curriculum_path: Path | None = None,
    model: str | None = None,
) -> dict:
    """
    Simpler agentic approach using query() with Read and Bash tools.
    
    Claude can read curriculum.md directly and run Python scripts as needed.
    This doesn't require custom MCP tools but gives Claude the same autonomy.
    
    Args:
        request: MCQ generation request
        curriculum_path: Path to curriculum.md
        model: Optional model override
    
    Returns:
        Generation result with MCQ content
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {
            "error": "claude-agent-sdk not installed. Install with: pip install claude-agent-sdk",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic_simple",
        }
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic_simple",
        }
    
    # Default curriculum path
    if curriculum_path is None:
        curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    # Get substandard info from request
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    difficulty = request.get("difficulty", "easy")
    
    # Build prompt that tells Claude what tools are available
    prompt = f"""Generate a Grade 3 ELA multiple-choice question for this request:

{json.dumps(request, indent=2)}

AVAILABLE TOOLS AND WORKFLOW:
You have access to Read and Bash tools. Here's how to get curriculum context:

1. READ the curriculum file to find the standard:
   - File path: {curriculum_path}
   - Search for "Standard ID: {substandard_id}"
   - Look for "Assessment Boundaries:" section
   - Look for "Common Misconceptions:" section

2. If the curriculum data shows "*None specified*", you can populate it by running:
   python -c "
import asyncio
import sys
sys.path.insert(0, '{curriculum_path.parent.parent}')
from src.populate_curriculum import populate_curriculum_entry
from pathlib import Path
result = asyncio.run(populate_curriculum_entry('{substandard_id}', Path('{curriculum_path}')))
print(result)
"

3. After getting curriculum context, generate an MCQ that:
   - Stays within the assessment boundaries
   - Uses common misconceptions as distractors
   - Matches difficulty: {difficulty}

Return ONLY a valid JSON object at the end:
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

    try:
        result_text = ""
        result_item = None
        parse_error = None
        tools_used = []
        
        # Create query generator - Claude will decide what tools to use
        query_gen = query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                allowed_tools=["Read", "Bash", "Glob"],
                setting_sources=["project"],
            ),
        )
        
        # Consume entire generator
        async for message in query_gen:
            # Track tool usage
            if hasattr(message, "tool_use"):
                tool_info = {
                    "name": getattr(message.tool_use, "name", "unknown"),
                    "input": getattr(message.tool_use, "input", {}),
                }
                tools_used.append(tool_info)
                logger.info(f"Claude called tool: {tool_info['name']}")
            
            # Capture final result
            if hasattr(message, "result"):
                result_text = str(message.result)
        
        # Extract JSON from response
        if result_text:
            js = _extract_json(result_text)
            try:
                parsed = json.loads(js)
                result_item = _parsed_to_item(parsed, request)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON: {e}")
                parse_error = str(e)
        
        if result_item:
            return {
                "error": None,
                "success": True,
                "timestamp": _utc_ts(),
                "generatedContent": {"generated_content": [result_item]},
                "generation_mode": "agentic_simple",
                "tools_used": tools_used,  # Track what Claude decided to use
            }
        
        return {
            "error": parse_error or "No valid JSON found in response",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic_simple",
            "tools_used": tools_used,
        }
        
    except Exception as e:
        logger.exception("Agentic simple generation failed")
        return {
            "error": str(e),
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic_simple",
        }
