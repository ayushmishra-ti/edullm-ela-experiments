"""
Option C: Agentic MCQ Generation using Claude Agent SDK.

This package provides fully agentic MCQ generation where Claude
autonomously calls tools to get curriculum context.

Usage:
    from option_c_agent_sdk import generate_mcq_agentic
    
    result = await generate_mcq_agentic(request)
"""

from .generate import generate_mcq_agentic
from .tools import (
    create_curriculum_mcp_server,
    lookup_curriculum,
    populate_curriculum,
    TOOL_NAMES,
)

__all__ = [
    "generate_mcq_agentic",
    "create_curriculum_mcp_server",
    "lookup_curriculum",
    "populate_curriculum",
    "TOOL_NAMES",
]
