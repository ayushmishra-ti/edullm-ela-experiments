"""
Truly Agentic MCQ Generation Pipeline using Claude Agent SDK.

This pipeline lets Claude autonomously decide:
1. When to look up curriculum data
2. When to populate missing curriculum data
3. How to use the context to generate high-quality MCQs

Unlike the skill-based approach, this uses Claude Agent SDK with MCP tools
where Claude has full autonomy over tool usage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _update_curriculum_file(
    curriculum_path: Path,
    standard_id: str,
    assessment_boundaries: str,
    common_misconceptions: list,
) -> bool:
    """Update curriculum.md with new data."""
    if not curriculum_path.exists():
        return False
    
    try:
        content = curriculum_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error reading curriculum file: {e}")
        return False
    
    # Split by "---" to get entries
    parts = content.split("---")
    updated = False
    
    for i, entry in enumerate(parts):
        if f"Standard ID: {standard_id}" in entry:
            original_entry = entry
            
            # Update Assessment Boundaries
            if assessment_boundaries:
                ab_pattern = r"(Assessment Boundaries:\s*)(?:\*None specified\*|.*?)(?=\n\nCommon Misconceptions:)"
                boundaries_text = assessment_boundaries.strip()
                replacement = f"\\1{boundaries_text}\n"
                entry = re.sub(ab_pattern, replacement, entry, flags=re.DOTALL)
            
            # Update Common Misconceptions
            if common_misconceptions:
                misconceptions_text = "\n".join([f"* {m.strip()}" for m in common_misconceptions if m.strip()])
                cm_pattern = r"(Common Misconceptions:\s*)(?:\*None specified\*|.*?)(?=\n\nDifficulty Definitions:)"
                replacement = f"\\1{misconceptions_text}\n"
                entry = re.sub(cm_pattern, replacement, entry, flags=re.DOTALL)
            
            if entry != original_entry:
                parts[i] = entry
                updated = True
                break
    
    if updated:
        new_content = "---".join(parts)
        try:
            curriculum_path.write_text(new_content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Error writing curriculum file: {e}")
            return False
    
    return False


# ============================================================================
# MCP Server Setup
# ============================================================================

def create_mcp_server_with_tools(curriculum_path: Path | None = None, scripts_dir: Path | None = None):
    """
    Create an in-process MCP server with curriculum tools.
    
    This allows Claude to call our custom tools (lookup_curriculum, populate_curriculum)
    during the agent loop.
    
    Args:
        curriculum_path: Path to curriculum.md (optional, uses default)
        scripts_dir: Path to scripts directory (optional, uses default)
    
    Returns:
        MCP server instance
    """
    try:
        from claude_agent_sdk import create_sdk_mcp_server, tool
    except ImportError:
        raise ImportError(
            "claude-agent-sdk not installed. Install with: pip install claude-agent-sdk"
        )
    
    # Default paths
    if curriculum_path is None:
        curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    if scripts_dir is None:
        scripts_dir = Path(__file__).parent.parent / ".claude" / "skills" / "ela-mcq-pipeline" / "scripts"
    
    # Tool 1: Lookup Curriculum
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
        script_path = scripts_dir / "lookup_curriculum.py"
        if not script_path.exists():
            return {"content": [{"type": "text", "text": json.dumps({"success": False, "error": "Script not found"})}]}
        
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), args["substandard_id"]],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(scripts_dir.parent.parent.parent.parent),
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
            else:
                data = {"success": False, "error": result.stderr}
        except Exception as e:
            data = {"success": False, "error": str(e)}
        
        return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}
    
    # Tool 2: Populate Curriculum
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
    async def populate_curriculum_tool_inner(args: dict) -> dict:
        """Generate and save curriculum data using Claude API."""
        import anthropic
        
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return {"content": [{"type": "text", "text": json.dumps({"success": False, "error": "ANTHROPIC_API_KEY not set"})}]}
        
        substandard_id = args["substandard_id"]
        standard_description = args["standard_description"]
        
        # Generate prompt
        prompt = f"""Generate Assessment Boundaries and Common Misconceptions for this ELA standard:

Standard ID: {substandard_id}
Standard Description: {standard_description}

Generate:

1. **Assessment Boundaries**: 1-3 concise bullet points specifying what IS and is NOT assessed.
   - Each bullet starts with "* " (asterisk + space)
   - Keep each bullet to 1-2 sentences max
   - Focus on grade-appropriate scope

2. **Common Misconceptions**: 3-5 bullet points of typical student errors.
   - Each bullet starts with "* " (asterisk + space)
   - One specific misconception per bullet
   - Useful for creating MCQ distractors

Return ONLY a JSON object:
{{
  "assessment_boundaries": "* Assessment is limited to...\\n* Students should...",
  "common_misconceptions": [
    "Students may confuse...",
    "Students often think...",
    "Students might incorrectly believe..."
  ]
}}"""
        
        try:
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            
            # Extract JSON from response
            text = ""
            if hasattr(response, "content"):
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text
                    elif isinstance(block, dict) and block.get("type") == "text":
                        text += block.get("text", "")
            
            # Parse JSON
            json_match = re.search(r'\{[\s\S]*"assessment_boundaries"[\s\S]*"common_misconceptions"[\s\S]*\}', text)
            if json_match:
                generated_data = json.loads(json_match.group(0))
            else:
                # Try parsing entire text
                generated_data = json.loads(text)
            
            # Save to curriculum.md
            updated = _update_curriculum_file(
                curriculum_path,
                substandard_id,
                generated_data.get("assessment_boundaries", ""),
                generated_data.get("common_misconceptions", []),
            )
            
            return {"content": [{"type": "text", "text": json.dumps({
                "success": True,
                "substandard_id": substandard_id,
                "assessment_boundaries": generated_data.get("assessment_boundaries"),
                "common_misconceptions": generated_data.get("common_misconceptions"),
                "file_updated": updated,
            }, indent=2)}]}
                
        except Exception as e:
            logger.exception(f"populate_curriculum_tool error: {e}")
            return {"content": [{"type": "text", "text": json.dumps({
                "success": False,
                "error": str(e)
            })}]}
    
    # Wrap populate_curriculum to capture curriculum_path
    async def populate_curriculum_tool(args: dict) -> dict:
        return await populate_curriculum_tool_inner(args)
    
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
    scripts_dir: Path | None = None,
    model: str | None = None,
    verbose: bool = False,
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
        scripts_dir: Path to scripts directory
        model: Optional model override
        verbose: Enable verbose logging
    
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
    
    # Default paths
    if curriculum_path is None:
        curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    if scripts_dir is None:
        scripts_dir = Path(__file__).parent.parent / ".claude" / "skills" / "ela-mcq-pipeline" / "scripts"
    
    # Get substandard info from request
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    substandard_description = skills.get("substandard_description", "")
    difficulty = request.get("difficulty", "easy")
    grade = request.get("grade", "3")
    qtype = request.get("type", "mcq")
    
    # Build the prompt - Force tool usage to prevent deadlocks
    prompt = f"""Generate a Grade {grade} ELA {qtype.upper()} question for this request:

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

3. FINALLY: Generate a {qtype.upper()} that:
   - Stays within the assessment boundaries from the curriculum data
   - Uses common misconceptions to create effective distractors
   - Matches the difficulty level: {difficulty}
   - Follows the output schema for {qtype.upper()} type

CRITICAL: Do not generate the question until you have curriculum context from the tools.
Start by calling lookup_curriculum NOW.

Return ONLY a valid JSON object matching this schema:
{{
  "id": "l_3_1_a_{qtype}_{difficulty}_001",
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
        if verbose:
            logger.info("Creating MCP server with curriculum tools...")
        try:
            mcp_server = create_mcp_server_with_tools(curriculum_path, scripts_dir)
            if verbose:
                logger.info("MCP server created successfully")
        except Exception as e:
            logger.exception(f"Failed to create MCP server: {e}")
            raise
        
        # Use query() with MCP server - Claude will decide when to call tools
        result_text = ""
        result_item = None
        parse_error = None
        tools_used = []
        
        # Create query generator with custom MCP tools
        try:
            query_gen = query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    mcp_servers=[mcp_server],  # List of MCP servers
                    setting_sources=["project"],  # Load skills from SKILL.md files
                ),
            )
        except TypeError:
            # If list doesn't work, try dict format
            query_gen = query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    mcp_servers={"curriculum-tools": mcp_server},  # Dict format
                    setting_sources=["project"],
                ),
            )
        except Exception as e:
            logger.exception(f"Failed to create query generator: {e}")
            raise
        
        # Consume entire generator - Claude will call tools as needed
        timeout_seconds = 180  # 3 minutes max per generation
        
        try:
            async with asyncio.timeout(timeout_seconds):
                async for message in query_gen:
                    # Track tool usage
                    if hasattr(message, "tool_use"):
                        tool_use = message.tool_use
                        tool_name = getattr(tool_use, "name", None) or getattr(tool_use, "tool_name", "unknown")
                        tools_used.append({"name": tool_name})
                        if verbose:
                            logger.info(f"Claude called tool: {tool_name}")
                    
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
            raise RuntimeError(error_msg)
        
        # Extract JSON from the final response
        if result_text:
            js = _extract_json(result_text)
            try:
                parsed = json.loads(js)
                result_item = _parsed_to_item(parsed, request)
                if verbose:
                    logger.info("Question generated successfully")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON: {e}")
                parse_error = str(e)
        
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
        return {
            "error": error_msg,
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
        }
