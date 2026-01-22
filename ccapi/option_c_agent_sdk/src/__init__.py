"""
Option C: Claude Agent SDK - Source Code

Core modules for curriculum lookup, population, and MCQ generation.

Two approaches available:
1. DEPRECATED (pipeline_agent_sdk): Python orchestrates, Claude generates text
   - Use `ccapi.pipeline_with_curriculum.generate_one_with_curriculum()` instead
2. Agentic (agentic_pipeline): Claude decides when to call tools autonomously
   - This is the recommended approach for this folder
"""

from .curriculum_lookup import lookup_curriculum
from .populate_curriculum import populate_curriculum_entry, update_curriculum_file
from .pipeline_agent_sdk import generate_one_agent_sdk
from .save_outputs import (
    get_outputs_dir,
    save_mcq_result,
    save_curriculum_lookup,
    save_batch_results,
)
from .tool_curriculum_lookup import create_curriculum_lookup_tool

# Agentic approach - Claude decides tool usage
from .agentic_tools import (
    tool_lookup_curriculum,
    tool_populate_curriculum,
    get_tool_definitions,
)
from .agentic_pipeline import (
    generate_one_agentic,
    generate_one_agentic_simple,
    create_mcp_server_with_tools,
)

__all__ = [
    # Original approach
    "lookup_curriculum",
    "populate_curriculum_entry",
    "update_curriculum_file",
    "generate_one_agent_sdk",
    "get_outputs_dir",
    "save_mcq_result",
    "save_curriculum_lookup",
    "save_batch_results",
    "create_curriculum_lookup_tool",
    # Agentic approach
    "tool_lookup_curriculum",
    "tool_populate_curriculum",
    "get_tool_definitions",
    "generate_one_agentic",
    "generate_one_agentic_simple",
    "create_mcp_server_with_tools",
]
