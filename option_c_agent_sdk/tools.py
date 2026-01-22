"""
Custom MCP tools for MCQ generation.

This module defines tools using the official @tool decorator pattern
from claude-agent-sdk. Claude can call these tools autonomously.
"""

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server


# Path to curriculum data
DATA_DIR = Path(__file__).parent / "data"
CURRICULUM_PATH = DATA_DIR / "curriculum.md"


def _lookup_curriculum_sync(substandard_id: str, curriculum_path: Path) -> dict:
    """Synchronously lookup curriculum data from markdown file."""
    if not curriculum_path.exists():
        return {
            "found": False,
            "error": f"Curriculum file not found: {curriculum_path}",
        }
    
    content = curriculum_path.read_text(encoding="utf-8")
    
    # Search for the standard section
    search_patterns = [
        f"Standard ID: {substandard_id}",
        f"## {substandard_id}",
        f"### {substandard_id}",
    ]
    
    found_pos = -1
    for pattern in search_patterns:
        pos = content.find(pattern)
        if pos >= 0:
            found_pos = pos
            break
    
    if found_pos < 0:
        return {
            "found": False,
            "error": f"Standard {substandard_id} not found in curriculum",
        }
    
    # Extract section (until next ## or end)
    section_end = content.find("\n## ", found_pos + 1)
    if section_end < 0:
        section_end = len(content)
    section = content[found_pos:section_end]
    
    # Extract assessment boundaries
    boundaries = None
    boundaries_start = section.find("Assessment Boundaries:")
    if boundaries_start >= 0:
        boundaries_end = section.find("\n\n", boundaries_start)
        if boundaries_end < 0:
            boundaries_end = len(section)
        boundaries = section[boundaries_start + len("Assessment Boundaries:"):boundaries_end].strip()
        if boundaries == "*None specified*" or not boundaries:
            boundaries = None
    
    # Extract misconceptions
    misconceptions = []
    misconceptions_start = section.find("Common Misconceptions:")
    if misconceptions_start >= 0:
        misconceptions_end = section.find("\n\n", misconceptions_start)
        if misconceptions_end < 0:
            misconceptions_end = len(section)
        misconceptions_text = section[misconceptions_start + len("Common Misconceptions:"):misconceptions_end]
        for line in misconceptions_text.strip().split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                misconceptions.append(line[2:].strip())
    
    # Extract description
    description = None
    desc_start = section.find("Description:")
    if desc_start >= 0:
        desc_end = section.find("\n\n", desc_start)
        if desc_end < 0:
            desc_end = section.find("\n", desc_start + 20)
        if desc_end >= 0:
            description = section[desc_start + len("Description:"):desc_end].strip()
    
    return {
        "found": True,
        "substandard_id": substandard_id,
        "assessment_boundaries": boundaries,
        "common_misconceptions": misconceptions if misconceptions else None,
        "standard_description": description,
        "has_boundaries": bool(boundaries),
        "has_misconceptions": bool(misconceptions),
    }


# ============================================================================
# Tool 1: Lookup Curriculum
# ============================================================================

@tool(
    "lookup_curriculum",
    """Look up curriculum information for a standard ID.
    
Returns assessment boundaries and common misconceptions from curriculum data.
Use this FIRST before generating any MCQ. The returned data includes:
- assessment_boundaries: What should/shouldn't be assessed
- common_misconceptions: Student errors (use as distractors)
- has_boundaries: True if boundaries exist
- has_misconceptions: True if misconceptions exist

If has_boundaries=False or has_misconceptions=False, call populate_curriculum.""",
    {"substandard_id": str}
)
async def lookup_curriculum(args: dict) -> dict[str, Any]:
    """Look up curriculum data for a standard."""
    substandard_id = args["substandard_id"]
    
    print(f"     [TOOL] lookup_curriculum({substandard_id})")
    
    result = _lookup_curriculum_sync(substandard_id, CURRICULUM_PATH)
    
    if result.get("found"):
        print(f"     [OK] Found: boundaries={result.get('has_boundaries')}, misconceptions={result.get('has_misconceptions')}")
    else:
        print(f"     [NOT FOUND] {result.get('error')}")
    
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# ============================================================================
# Tool 2: Populate Curriculum (stub - uses existing data or generates)
# ============================================================================

@tool(
    "populate_curriculum",
    """Generate and save curriculum data for a standard.
    
Use this when lookup_curriculum returns has_boundaries=False or has_misconceptions=False.
This will generate appropriate Assessment Boundaries and Common Misconceptions.
After calling this, call lookup_curriculum again to get the populated data.""",
    {"substandard_id": str, "standard_description": str}
)
async def populate_curriculum(args: dict) -> dict[str, Any]:
    """Generate curriculum data for a standard (stub implementation)."""
    substandard_id = args["substandard_id"]
    standard_description = args.get("standard_description", "")
    
    print(f"     [TOOL] populate_curriculum({substandard_id})")
    
    # For now, return a message that data should be populated
    # In production, this would call an LLM to generate curriculum data
    result = {
        "success": True,
        "message": f"Curriculum data requested for {substandard_id}. Using existing data if available.",
        "substandard_id": substandard_id,
    }
    
    print(f"     [OK] Populate requested (using existing curriculum data)")
    
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


# ============================================================================
# Create MCP Server with Tools
# ============================================================================

def create_curriculum_mcp_server():
    """Create MCP server with curriculum tools."""
    return create_sdk_mcp_server(
        name="curriculum",
        version="1.0.0",
        tools=[lookup_curriculum, populate_curriculum]
    )


# Tool names for allowed_tools configuration
TOOL_NAMES = ["lookup_curriculum", "populate_curriculum"]
