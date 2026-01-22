"""
Custom MCP tools for the agentic MCQ generation pipeline.

These tools allow Claude to autonomously decide when to:
1. Look up curriculum data
2. Populate missing curriculum data
3. Generate MCQs with proper context

The tools are defined using the @tool decorator and run in-process
for better performance and direct access to application state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Import the underlying functions
from .curriculum_lookup import lookup_curriculum
from .populate_curriculum import generate_curriculum_content, update_curriculum_file


def get_default_curriculum_path() -> Path:
    """Get the default curriculum.md path."""
    return Path(__file__).parent.parent / "data" / "curriculum.md"


# ============================================================================
# Tool 1: Curriculum Lookup
# ============================================================================

async def tool_lookup_curriculum(substandard_id: str, curriculum_path: str | None = None) -> dict[str, Any]:
    """
    Look up curriculum information for a given standard ID.
    
    This tool searches curriculum.md and returns:
    - Assessment Boundaries: What should/shouldn't be assessed
    - Common Misconceptions: Typical student errors (useful for distractors)
    - Standard Description: The full description of the standard
    
    Args:
        substandard_id: The standard ID (e.g., "CCSS.ELA-LITERACY.L.3.1.A")
        curriculum_path: Optional path to curriculum.md (uses default if not provided)
    
    Returns:
        Dictionary with curriculum information or error message
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔍 Tool: lookup_curriculum called with substandard_id={substandard_id}")
    print(f"     🔍 Executing lookup_curriculum({substandard_id})...")
    
    path = Path(curriculum_path) if curriculum_path else get_default_curriculum_path()
    result = lookup_curriculum(substandard_id, path)
    
    # Return a clean summary for Claude
    if result.get("found"):
        has_boundaries = bool(result.get("assessment_boundaries"))
        has_misconceptions = bool(result.get("common_misconceptions"))
        
        print(f"     ✓ Found curriculum data (boundaries={has_boundaries}, misconceptions={has_misconceptions})")
        logger.info(f"lookup_curriculum found data: boundaries={has_boundaries}, misconceptions={has_misconceptions}")
        
        return {
            "success": True,
            "substandard_id": substandard_id,
            "standard_description": result.get("standard_description"),
            "assessment_boundaries": result.get("assessment_boundaries"),
            "common_misconceptions": result.get("common_misconceptions"),
            "has_boundaries": has_boundaries,
            "has_misconceptions": has_misconceptions,
        }
    else:
        error_msg = result.get("error", f"Standard {substandard_id} not found")
        print(f"     ✗ Not found: {error_msg}")
        logger.warning(f"lookup_curriculum not found: {error_msg}")
        
        return {
            "success": False,
            "substandard_id": substandard_id,
            "error": error_msg,
        }


# ============================================================================
# Tool 2: Populate Curriculum (generates missing data)
# ============================================================================

async def tool_populate_curriculum(
    substandard_id: str,
    standard_description: str,
    curriculum_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate and save Assessment Boundaries and Common Misconceptions for a standard.
    
    Use this tool when curriculum lookup returns empty/missing data.
    This will:
    1. Generate appropriate Assessment Boundaries
    2. Generate Common Misconceptions (useful for MCQ distractors)
    3. Save the data to curriculum.md for future reuse
    
    Args:
        substandard_id: The standard ID (e.g., "CCSS.ELA-LITERACY.L.3.1.A")
        standard_description: The description of the standard
        curriculum_path: Optional path to curriculum.md
    
    Returns:
        Dictionary with generated content or error
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"📝 Tool: populate_curriculum called with substandard_id={substandard_id}")
    print(f"     📝 Executing populate_curriculum({substandard_id})...")
    print(f"     Generating curriculum data (this may take a moment)...")
    
    path = Path(curriculum_path) if curriculum_path else get_default_curriculum_path()
    
    try:
        # Generate the curriculum content
        generated = await generate_curriculum_content(
            substandard_id,
            standard_description,
        )
        
        if generated.get("error"):
            error_msg = generated.get("error")
            print(f"     ✗ Error generating curriculum: {error_msg}")
            logger.error(f"populate_curriculum error: {error_msg}")
            return {
                "success": False,
                "substandard_id": substandard_id,
                "error": error_msg,
            }
        
        # Update the curriculum file
        updated = update_curriculum_file(
            path,
            substandard_id,
            generated.get("assessment_boundaries"),
            generated.get("common_misconceptions"),
        )
        
        print(f"     ✓ Successfully populated and saved curriculum data")
        logger.info(f"populate_curriculum success: file_updated={updated}")
        
        return {
            "success": True,
            "substandard_id": substandard_id,
            "assessment_boundaries": generated.get("assessment_boundaries"),
            "common_misconceptions": generated.get("common_misconceptions"),
            "file_updated": updated,
            "message": f"Successfully populated curriculum data for {substandard_id}",
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"     ✗ Exception: {error_msg}")
        logger.exception(f"populate_curriculum exception: {error_msg}")
        return {
            "success": False,
            "substandard_id": substandard_id,
            "error": error_msg,
        }


# ============================================================================
# Tool Definitions for MCP Server
# ============================================================================

def get_tool_definitions() -> list[dict[str, Any]]:
    """
    Get tool definitions in the format expected by Claude Agent SDK.
    
    Returns a list of tool definitions that can be passed to create_sdk_mcp_server().
    """
    return [
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
            },
            "executor": tool_lookup_curriculum,
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
                        "description": "The standard ID (e.g., 'CCSS.ELA-LITERACY.L.3.1.A')"
                    },
                    "standard_description": {
                        "type": "string",
                        "description": "The description of the standard"
                    }
                },
                "required": ["substandard_id", "standard_description"]
            },
            "executor": tool_populate_curriculum,
        },
    ]
