"""
Option C: Claude Agent SDK implementation.

This module provides MCQ generation using Claude Agent SDK with curriculum lookup tools.

Two approaches available:

1. Original (generate_one_agent_sdk):
   - Python orchestrates the workflow
   - Claude only generates the final MCQ text
   - Workflow: Python calls lookup → Python calls populate → Python calls Claude
   
2. Agentic (generate_one_agentic):
   - Claude decides when to call tools autonomously
   - Claude orchestrates the entire workflow
   - Workflow: Claude decides → Claude calls lookup tool → Claude calls populate tool → Claude generates MCQ
"""

# Re-export from src module
from .src import (
    # Original approach (Python orchestrates)
    lookup_curriculum,
    generate_one_agent_sdk,
    populate_curriculum_entry,
    update_curriculum_file,
    get_outputs_dir,
    save_mcq_result,
    save_curriculum_lookup,
    save_batch_results,
    create_curriculum_lookup_tool,
    # Agentic approach (Claude orchestrates)
    tool_lookup_curriculum,
    tool_populate_curriculum,
    get_tool_definitions,
    generate_one_agentic,
    generate_one_agentic_simple,
    create_mcp_server_with_tools,
)

__all__ = [
    # Original approach
    "lookup_curriculum",
    "generate_one_agent_sdk",
    "populate_curriculum_entry",
    "update_curriculum_file",
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
