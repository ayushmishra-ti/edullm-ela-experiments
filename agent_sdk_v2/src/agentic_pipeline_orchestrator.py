"""
Agentic ELA Pipeline - Claude as Orchestrator

Architecture:
- Claude is the ORCHESTRATOR (not just a worker)
- Python provides META-TOOLS for Claude to control the flow
- Claude decides: which skills to use, when to spawn sub-agents, when to finish

Meta-Tools given to Claude:
1. read_skill(name) - Load a SKILL.md file
2. spawn_agent(skill, message) - Spawn a sub-agent with a skill
3. cache_get/cache_set - Manage caching
4. complete(result) - Signal completion with final result

Flow:
1. Claude receives the request
2. Claude decides to read_skill("ela-question-generation")
3. Claude reads the skill and decides next steps
4. If needed, Claude spawns sub-agents for passage generation
5. Claude calls complete() with the final question JSON

Key Principle: Claude orchestrates, Python just provides capabilities.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ============================================================================
# Meta-Tools: Capabilities Claude can use to orchestrate
# ============================================================================

ORCHESTRATOR_TOOLS = [
    {
        "name": "read_skill",
        "description": """Read a SKILL.md file to get instructions for a specific task.
        
Available skills:
- "ela-question-generation": Main skill for generating ELA questions
- "generate-passage": Skill for generating reading passages (for RL.*/RI.* standards)
- "populate-curriculum": Skill for generating curriculum data

Call this first to understand how to handle the task.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to load",
                    "enum": ["ela-question-generation", "generate-passage", "populate-curriculum"]
                }
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "spawn_agent",
        "description": """Spawn a sub-agent to perform a specific task.
        
The sub-agent will use the specified skill as its instructions and process the message.
Use this for delegating work like passage generation.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The skill for the sub-agent to use"
                },
                "message": {
                    "type": "string",
                    "description": "The task/request for the sub-agent"
                }
            },
            "required": ["skill_name", "message"]
        }
    },
    {
        "name": "cache_get",
        "description": "Get a cached value by key. Returns null if not found.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Cache key (e.g., standard_id for passages)"
                },
                "cache_type": {
                    "type": "string",
                    "enum": ["passage", "curriculum"],
                    "description": "Type of cache to check"
                }
            },
            "required": ["key", "cache_type"]
        }
    },
    {
        "name": "cache_set",
        "description": "Save a value to cache.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Cache key"
                },
                "cache_type": {
                    "type": "string",
                    "enum": ["passage", "curriculum"]
                },
                "value": {
                    "type": "string",
                    "description": "Value to cache"
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata to store"
                }
            },
            "required": ["key", "cache_type", "value"]
        }
    },
    {
        "name": "complete",
        "description": """Signal that orchestration is complete and return the final result.
        
IMPORTANT: Call this when you have the final question JSON ready.
The result should be the complete question object with id and content.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "object",
                    "description": "The final result (question JSON with id and content)"
                },
                "success": {
                    "type": "boolean",
                    "description": "Whether the task succeeded"
                },
                "error": {
                    "type": "string",
                    "description": "Error message if failed"
                }
            },
            "required": ["success"]
        }
    },
]


# ============================================================================
# Tool Execution (Python provides capabilities)
# ============================================================================

class OrchestratorRuntime:
    """
    Runtime that provides capabilities to Claude (the orchestrator).
    
    Claude calls tools, this class executes them.
    """
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = None
        self._completed = False
        self._final_result = None
    
    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client
    
    @property
    def is_completed(self) -> bool:
        return self._completed
    
    @property
    def final_result(self) -> dict | None:
        return self._final_result
    
    async def execute_tool(self, name: str, inputs: dict) -> dict:
        """Execute a meta-tool and return result."""
        
        if name == "read_skill":
            return self._read_skill(inputs)
        
        elif name == "spawn_agent":
            return await self._spawn_agent(inputs)
        
        elif name == "cache_get":
            return self._cache_get(inputs)
        
        elif name == "cache_set":
            return self._cache_set(inputs)
        
        elif name == "complete":
            return self._complete(inputs)
        
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}
    
    def _read_skill(self, inputs: dict) -> dict:
        """Read a SKILL.md file."""
        skill_name = inputs.get("skill_name", "")
        skill_path = ROOT / ".claude" / "skills" / skill_name / "SKILL.md"
        
        if not skill_path.exists():
            return {"success": False, "error": f"Skill not found: {skill_name}"}
        
        try:
            content = skill_path.read_text(encoding="utf-8")
            return {
                "success": True,
                "skill_name": skill_name,
                "content": content,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _spawn_agent(self, inputs: dict) -> dict:
        """Spawn a sub-agent with a skill."""
        skill_name = inputs.get("skill_name", "")
        message = inputs.get("message", "")
        
        # Load the skill
        skill_result = self._read_skill({"skill_name": skill_name})
        if not skill_result.get("success"):
            return skill_result
        
        skill_content = skill_result["content"]
        
        # Call Claude as sub-agent (simple call, no tools)
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=skill_content,
                messages=[{"role": "user", "content": message}],
            )
            
            # Extract text
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            
            return {
                "success": True,
                "skill_used": skill_name,
                "response": text.strip(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _cache_get(self, inputs: dict) -> dict:
        """Get from cache."""
        key = inputs.get("key", "")
        cache_type = inputs.get("cache_type", "passage")
        
        if cache_type == "passage":
            cache_dir = ROOT / "data" / "passages"
        else:
            cache_dir = ROOT / "data" / "curriculum"
        
        safe_key = key.replace(".", "_").replace(":", "_").replace("/", "_")
        cache_path = cache_dir / f"{safe_key}.json"
        
        if not cache_path.exists():
            return {"success": True, "found": False, "value": None}
        
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return {
                "success": True,
                "found": True,
                "value": data.get("text") or data.get("content"),
                "metadata": data,
            }
        except Exception:
            return {"success": True, "found": False, "value": None}
    
    def _cache_set(self, inputs: dict) -> dict:
        """Set cache value."""
        key = inputs.get("key", "")
        cache_type = inputs.get("cache_type", "passage")
        value = inputs.get("value", "")
        metadata = inputs.get("metadata", {})
        
        if cache_type == "passage":
            cache_dir = ROOT / "data" / "passages"
        else:
            cache_dir = ROOT / "data" / "curriculum"
        
        cache_dir.mkdir(parents=True, exist_ok=True)
        safe_key = key.replace(".", "_").replace(":", "_").replace("/", "_")
        cache_path = cache_dir / f"{safe_key}.json"
        
        try:
            payload = {
                "text": value,
                "cached_at": utc_timestamp(),
                **metadata,
            }
            cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return {"success": True, "cached": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _complete(self, inputs: dict) -> dict:
        """Signal completion."""
        self._completed = True
        self._final_result = {
            "success": inputs.get("success", False),
            "result": inputs.get("result"),
            "error": inputs.get("error"),
        }
        return {"acknowledged": True, "message": "Orchestration complete"}


# ============================================================================
# Orchestrator System Prompt
# ============================================================================

ORCHESTRATOR_SYSTEM_PROMPT = """You are an AI Orchestrator for ELA question generation.

YOUR ROLE: You control the entire workflow. You decide what to do, when to do it, and how to combine results.

AVAILABLE TOOLS:
1. read_skill(skill_name) - Read instructions from a SKILL.md file
2. spawn_agent(skill_name, message) - Spawn a sub-agent to do work
3. cache_get(key, cache_type) - Check if something is cached
4. cache_set(key, cache_type, value) - Save to cache
5. complete(result, success) - Finish and return the final result

WORKFLOW:
1. First, read the "ela-question-generation" skill to understand the task
2. Analyze the request to determine what's needed
3. For RL.*/RI.* standards:
   a. Check cache for existing passage
   b. If not cached, spawn a sub-agent with "generate-passage" skill
   c. Cache the generated passage
4. Generate the question following the skill instructions
5. Call complete() with the final question JSON

IMPORTANT:
- You are in control. Decide the best approach.
- Always read the relevant skill first to understand requirements.
- Use caching to avoid redundant work.
- The final result must be valid JSON with "id" and "content" fields.

BEGIN: Analyze the request and orchestrate the workflow."""


# ============================================================================
# Main Orchestrator Function
# ============================================================================

@dataclass
class OrchestratorResult:
    """Result from orchestrator run."""
    success: bool
    content: Any = None
    error: str | None = None
    tools_used: list = field(default_factory=list)
    iterations: int = 0


async def run_orchestrator(
    request: dict,
    *,
    model: str | None = None,
    verbose: bool = False,
    max_iterations: int = 20,
) -> OrchestratorResult:
    """
    Run Claude as the orchestrator for ELA question generation.
    
    Claude controls the entire flow:
    - Reads skills
    - Spawns sub-agents
    - Manages caching
    - Decides when complete
    
    Python just provides the meta-tools.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return OrchestratorResult(success=False, error="ANTHROPIC_API_KEY not set")
    
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    
    # Initialize runtime (provides capabilities to Claude)
    runtime = OrchestratorRuntime(api_key, model)
    
    # Build the initial message
    user_message = f"""Please orchestrate the generation of an ELA question for this request:

{json.dumps(request, indent=2)}

Start by reading the appropriate skill, then follow the workflow to generate the question.
Call complete() when you have the final result."""
    
    messages = [{"role": "user", "content": user_message}]
    tools_used = []
    
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    except ImportError:
        return OrchestratorResult(success=False, error="anthropic not installed")
    
    for iteration in range(max_iterations):
        if verbose:
            logger.info(f"[Orchestrator] Iteration {iteration + 1}")
        
        # Call Claude (the orchestrator)
        response = await client.messages.create(
            model=model,
            max_tokens=8192,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            tools=ORCHESTRATOR_TOOLS,
            messages=messages,
        )
        
        if verbose:
            logger.info(f"[Orchestrator] Stop reason: {response.stop_reason}")
        
        if response.stop_reason == "end_turn":
            # Claude finished without calling complete() - extract text
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            
            return OrchestratorResult(
                success=False,
                error="Orchestrator ended without calling complete()",
                content=text,
                tools_used=tools_used,
                iterations=iteration + 1,
            )
        
        elif response.stop_reason == "tool_use":
            # Claude is using tools - execute them
            messages.append({"role": "assistant", "content": response.content})
            
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                
                tool_name = block.name
                tool_input = block.input
                
                if verbose:
                    logger.info(f"[Orchestrator] Tool: {tool_name}({json.dumps(tool_input)[:100]}...)")
                
                tools_used.append({"name": tool_name, "input": tool_input})
                
                # Execute the meta-tool
                result = await runtime.execute_tool(tool_name, tool_input)
                
                if verbose:
                    logger.info(f"[Orchestrator] Result: {str(result)[:200]}...")
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, indent=2),
                })
                
                # Check if orchestration is complete
                if runtime.is_completed:
                    final = runtime.final_result
                    return OrchestratorResult(
                        success=final.get("success", False),
                        content=final.get("result"),
                        error=final.get("error"),
                        tools_used=tools_used,
                        iterations=iteration + 1,
                    )
            
            messages.append({"role": "user", "content": tool_results})
        
        else:
            return OrchestratorResult(
                success=False,
                error=f"Unexpected stop reason: {response.stop_reason}",
                tools_used=tools_used,
                iterations=iteration + 1,
            )
    
    return OrchestratorResult(
        success=False,
        error=f"Max iterations ({max_iterations}) reached",
        tools_used=tools_used,
        iterations=max_iterations,
    )


# ============================================================================
# Convenience Function (Same interface as v2/v3)
# ============================================================================

async def generate_one_agentic(
    request: dict,
    *,
    model: str | None = None,
    verbose: bool = False,
) -> dict:
    """
    Generate one ELA question with Claude as orchestrator.
    
    Same interface as v2/v3 for drop-in replacement.
    """
    result = await run_orchestrator(request, model=model, verbose=verbose)
    
    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "timestamp": utc_timestamp(),
            "generatedContent": {"generated_content": []},
            "tools_used": result.tools_used,
            "iterations": result.iterations,
        }
    
    # Normalize the result
    content = result.content or {}
    if "content" in content:
        content["content"]["image_url"] = []
    
    return {
        "success": True,
        "error": None,
        "timestamp": utc_timestamp(),
        "generatedContent": {
            "generated_content": [{
                "id": content.get("id", ""),
                "content": content.get("content", {}),
                "request": request,
            }]
        },
        "tools_used": result.tools_used,
        "iterations": result.iterations,
    }
