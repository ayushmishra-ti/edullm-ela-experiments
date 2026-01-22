"""
Custom tool definition for Claude Agent SDK to lookup curriculum information.

This defines a tool that Claude can call autonomously during generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .curriculum_lookup import lookup_curriculum


def create_curriculum_lookup_tool(curriculum_path: Path | None = None) -> dict[str, Any]:
    """
    Create a tool definition for the Agent SDK that allows Claude to lookup
    curriculum information.
    
    Returns a tool definition compatible with Claude Agent SDK.
    """
    def tool_executor(substandard_id: str) -> dict[str, Any]:
        """
        Execute the curriculum lookup tool.
        
        Args:
            substandard_id: The standard ID to search for
        
        Returns:
            Dictionary with curriculum information
        """
        return lookup_curriculum(substandard_id, curriculum_path)
    
    # Return tool definition in the format expected by Agent SDK
    # Note: The exact format depends on the Agent SDK version
    # This is a placeholder - we'll need to adapt based on SDK documentation
    return {
        "name": "curriculum_lookup",
        "description": "Search the curriculum.md file for a given substandard_id and return assessment boundaries and common misconceptions. Use this tool before generating questions to ensure alignment with curriculum guidelines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "substandard_id": {
                    "type": "string",
                    "description": "The standard ID to search for (e.g., 'CCSS.ELA-LITERACY.L.3.1.A')"
                }
            },
            "required": ["substandard_id"]
        },
        "executor": tool_executor,
    }
