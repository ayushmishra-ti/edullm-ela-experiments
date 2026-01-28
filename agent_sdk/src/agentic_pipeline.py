"""
Truly Agentic MCQ Generation Pipeline using Anthropic API with Native Tool Use.

This pipeline lets Claude autonomously decide:
1. When to look up curriculum data
2. When to populate missing curriculum data
3. How to use the context to generate high-quality MCQs

Claude has full autonomy over tool usage via the native Anthropic tool_use feature.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

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

def _id_prefix_from_standard_id(substandard_id: str) -> str:
    """
    Convert a CCSS standard id into an item id prefix.

    Example:
      CCSS.ELA-LITERACY.L.3.1.A -> l_3_1_a
      CCSS.ELA-LITERACY.RI.5.2 -> ri_5_2
    """
    s = (substandard_id or "").strip()
    if not s:
        return "item"

    # Strip common prefix if present
    s = re.sub(r"^CCSS\.ELA-LITERACY\.", "", s, flags=re.IGNORECASE).strip()

    # Lowercase and normalize separators
    s = s.lower()
    s = s.replace("-", "_").replace(".", "_")
    s = re.sub(r"[^a-z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


# ============================================================================
# Tool Definitions (Anthropic Native Format)
# ============================================================================

TOOLS = [
    {
        "name": "lookup_curriculum",
        "description": """Look up curriculum information for a standard ID.

Returns assessment boundaries and common misconceptions from curriculum.md.
Use this FIRST before generating any MCQ to understand:
- What should and shouldn't be assessed (assessment boundaries)
- Common student errors to use as distractors (misconceptions)

If the returned data shows has_boundaries=False or has_misconceptions=False,
you should call populate_curriculum to generate the missing data.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "substandard_id": {
                    "type": "string",
                    "description": "The standard ID (e.g., 'CCSS.ELA-LITERACY.L.3.1.A')"
                }
            },
            "required": ["substandard_id"]
        }
    },
    {
        "name": "populate_curriculum",
        "description": """Generate and save curriculum data for a standard.

Use this when lookup_curriculum returns missing data (has_boundaries=False or has_misconceptions=False).
This tool will:
1. Generate appropriate Assessment Boundaries for the standard
2. Generate Common Misconceptions (useful for MCQ distractors)
3. Save the data to curriculum.md for future reuse

After calling this, use lookup_curriculum again to get the populated data.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "substandard_id": {
                    "type": "string",
                    "description": "The standard ID to populate"
                },
                "standard_description": {
                    "type": "string",
                    "description": "Description of what the standard covers"
                }
            },
            "required": ["substandard_id", "standard_description"]
        }
    }
]


# ============================================================================
# Tool Execution Functions
# ============================================================================

def execute_lookup_curriculum(args: dict, scripts_dir: Path) -> dict:
    """Execute lookup_curriculum tool."""
    script_path = scripts_dir / "lookup_curriculum.py"
    if not script_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), args["substandard_id"]],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(scripts_dir.parent.parent.parent.parent),
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_populate_curriculum(args: dict, scripts_dir: Path) -> dict:
    """Execute populate_curriculum tool."""
    script_path = scripts_dir / "populate_curriculum.py"
    if not script_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), args["substandard_id"], args["standard_description"]],
            capture_output=True,
            text=True,
            timeout=60,  # Longer timeout for API call
            cwd=str(scripts_dir.parent.parent.parent.parent),
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"success": False, "error": result.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_tool(tool_name: str, tool_input: dict, scripts_dir: Path) -> str:
    """Execute a tool and return the result as JSON string."""
    if tool_name == "lookup_curriculum":
        result = execute_lookup_curriculum(tool_input, scripts_dir)
    elif tool_name == "populate_curriculum":
        result = execute_populate_curriculum(tool_input, scripts_dir)
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    
    return json.dumps(result, indent=2)


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
    
    Uses Anthropic's native tool_use feature for Claude to call tools.
    
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
        import anthropic
    except ImportError:
        return {
            "error": "anthropic package not installed. Install with: pip install anthropic",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
        }
    
    # NOTE: Cloud secrets sometimes include trailing newlines; strip whitespace
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
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
        scripts_dir = Path(__file__).parent.parent / ".claude" / "skills" / "ela-question-generation" / "scripts"
    
    # Model
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    
    # Get substandard info from request
    skills = request.get("skills") or {}
    substandard_id = skills.get("substandard_id", "")
    substandard_description = skills.get("substandard_description", "")
    difficulty = request.get("difficulty", "easy")
    grade = request.get("grade", "3")
    qtype = request.get("type", "mcq")
    id_prefix = _id_prefix_from_standard_id(substandard_id)
    
    q = (qtype or "").strip().lower()
    if q in {"fill-in", "fill_in", "fillin", "fill"}:
        qtype_requirements = f"""   - Creates a single unambiguous blank (______) with exactly ONE reasonable answer
   - Does NOT include answer_options (fill-in questions have no options)
   - Sets content.additional_details to the standard id: "{substandard_id}"
   - Uses curriculum misconceptions to anticipate common wrong responses (in the explanation), without using option letters
   - CRITICAL: The answer_explanation MUST NOT reference nonexistent multiple-choice options like "Option A/B/C/D"
"""
        schema_example = f"""{{
  "id": "{id_prefix}_{qtype}_{difficulty}_001",
  "content": {{
    "answer": "...",
    "question": "... ______ ...",
    "image_url": [],
    "additional_details": "{substandard_id}",
    "answer_explanation": "..."
  }}
}}"""
    elif q in {"msq", "multi-select", "multi_select", "multiselect"}:
        qtype_requirements = """   - Includes answer_options with keys A-D
   - Uses curriculum misconceptions to create strong distractors
   - The question MUST say "Select all that apply" (or equivalent)
   - content.answer MUST be an array of keys, e.g. ["A","C"]
"""
        schema_example = f"""{{
  "id": "{id_prefix}_{qtype}_{difficulty}_001",
  "content": {{
    "answer": ["A", "C"],
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
    else:
        # Default to MCQ schema
        qtype_requirements = """   - Includes answer_options with keys A-D
   - Uses curriculum misconceptions to create strong distractors
   - content.answer MUST be a single key like "B"
"""
        schema_example = f"""{{
  "id": "{id_prefix}_{qtype}_{difficulty}_001",
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

    # Build the initial prompt
    user_prompt = f"""Generate a Grade {grade} ELA {qtype.upper()} question for this request:

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
   - Matches the difficulty level: {difficulty}
   - Follows the output schema for {qtype.upper()} type
   - Uses an item id derived from the standard id: "{id_prefix}"
{qtype_requirements}

CRITICAL: Do not generate the question until you have curriculum context from the tools.
Start by calling lookup_curriculum NOW.

Return ONLY a valid JSON object matching this schema:
{schema_example}

No markdown code fences in your final answer, just the JSON object."""

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        messages = [{"role": "user", "content": user_prompt}]
        tools_used = []
        max_iterations = 10  # Prevent infinite loops
        
        for iteration in range(max_iterations):
            if verbose:
                logger.info(f"Iteration {iteration + 1}: Calling Claude...")
            
            # Call Claude with tools
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                tools=TOOLS,
                messages=messages,
            )
            
            if verbose:
                logger.info(f"Stop reason: {response.stop_reason}")
            
            # Check if Claude wants to use a tool
            if response.stop_reason == "tool_use":
                # Find tool use blocks
                tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
                
                # Add assistant response to messages
                messages.append({"role": "assistant", "content": response.content})
                
                # Execute each tool and add results
                tool_results = []
                for tool_block in tool_use_blocks:
                    tool_name = tool_block.name
                    tool_input = tool_block.input
                    
                    if verbose:
                        logger.info(f"Claude called tool: {tool_name} with input: {tool_input}")
                    
                    tools_used.append({"name": tool_name, "input": tool_input})
                    
                    # Execute the tool
                    result = execute_tool(tool_name, tool_input, scripts_dir)
                    
                    if verbose:
                        logger.info(f"Tool result: {result[:200]}...")
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    })
                
                # Add tool results to messages
                messages.append({"role": "user", "content": tool_results})
                
            elif response.stop_reason == "end_turn":
                # Claude finished - extract the final response
                result_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        result_text += block.text
                
                if verbose:
                    logger.info(f"Final response: {result_text[:200]}...")
                
                # Parse JSON from the response
                if result_text:
                    js = _extract_json(result_text)
                    try:
                        parsed = json.loads(js)
                        result_item = _parsed_to_item(parsed, request)
                        
                        return {
                            "error": None,
                            "success": True,
                            "timestamp": _utc_ts(),
                            "generatedContent": {"generated_content": [result_item]},
                            "generation_mode": "agentic",
                            "tools_used": tools_used,
                        }
                    except json.JSONDecodeError as e:
                        return {
                            "error": f"Failed to parse JSON: {e}",
                            "success": False,
                            "timestamp": _utc_ts(),
                            "generatedContent": {"generated_content": []},
                            "generation_mode": "agentic",
                            "tools_used": tools_used,
                            "raw_response": result_text[:500],
                        }
                
                return {
                    "error": "No text in final response",
                    "success": False,
                    "timestamp": _utc_ts(),
                    "generatedContent": {"generated_content": []},
                    "generation_mode": "agentic",
                    "tools_used": tools_used,
                }
            
            else:
                # Unexpected stop reason
                return {
                    "error": f"Unexpected stop reason: {response.stop_reason}",
                    "success": False,
                    "timestamp": _utc_ts(),
                    "generatedContent": {"generated_content": []},
                    "generation_mode": "agentic",
                    "tools_used": tools_used,
                }
        
        # Max iterations reached
        return {
            "error": f"Max iterations ({max_iterations}) reached without completion",
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
            "tools_used": tools_used,
        }
        
    except Exception as e:
        logger.exception("Agentic generation failed")
        return {
            "error": str(e),
            "success": False,
            "timestamp": _utc_ts(),
            "generatedContent": {"generated_content": []},
            "generation_mode": "agentic",
        }
