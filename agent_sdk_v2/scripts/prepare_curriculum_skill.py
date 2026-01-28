#!/usr/bin/env python3
"""
Invoke the prepare-curriculum-batch skill to populate missing curriculum fields.

This is a SKILL-BASED workflow: Claude reads curriculum.md, detects missing fields,
generates content, and updates the file autonomously using the skill instructions.

Usage:
  cd agent_sdk_v2
  python scripts/prepare_curriculum_skill.py
  python scripts/prepare_curriculum_skill.py --limit 20
  python scripts/prepare_curriculum_skill.py --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parents[1]

# Add src to path
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass


async def run_prepare_curriculum(limit: int | None = None, verbose: bool = False) -> dict:
    """
    Invoke the prepare-curriculum-batch skill via Claude Agent SDK.
    
    Claude will:
    1. Read curriculum.md
    2. Find blocks with *None specified*
    3. Generate curriculum data
    4. Update curriculum.md in-place
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return {"success": False, "error": "claude_agent_sdk not installed"}

    # Build prompt that triggers the skill
    prompt = "Use the prepare-curriculum-batch skill to scan curriculum.md and populate any missing Learning Objectives, Assessment Boundaries, and Common Misconceptions fields."
    
    if limit:
        prompt += f"\n\nProcess only the first {limit} standards that need population (for testing)."
    
    prompt += "\n\nReport which standards you updated when done."

    # SDK options with required tools for this skill
    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        setting_sources=["user", "project"],
        allowed_tools=["Skill", "Read", "Write", "Bash"],  # Need Write to update curriculum.md
    )

    print("=" * 60)
    print("Prepare Curriculum (Skill-Based Workflow)")
    print("=" * 60)
    print(f"\nProject root: {ROOT}")
    print(f"Skill:        prepare-curriculum-batch")
    print(f"Limit:        {limit or 'all'}")
    print("\nStarting Claude Agent SDK...")
    print("-" * 60)

    result_content = None
    
    try:
        async for message in query(prompt=prompt, options=options):
            if verbose:
                msg_type = type(message).__name__
                print(f"[SDK] {msg_type}")
                
                # Show text content as it streams
                if hasattr(message, "content"):
                    content = message.content
                    if hasattr(content, "__iter__"):
                        for block in content:
                            if hasattr(block, "type"):
                                block_type = getattr(block, "type", "")
                                if block_type == "text":
                                    text = getattr(block, "text", "")
                                    if text:
                                        print(text, end="", flush=True)
                                elif block_type == "tool_use":
                                    tool_name = getattr(block, "name", "unknown")
                                    print(f"\n[TOOL] {tool_name}")
            
            # Capture final result
            if hasattr(message, "result"):
                result_content = message.result
            elif hasattr(message, "content"):
                result_content = message.content
            elif isinstance(message, str):
                result_content = message
        
        print("\n" + "-" * 60)
        print("Agent completed.")
        
        # Extract text from result
        if result_content:
            if isinstance(result_content, str):
                text = result_content
            elif hasattr(result_content, "__iter__"):
                text = ""
                for block in result_content:
                    if hasattr(block, "text"):
                        text += block.text
            else:
                text = str(result_content)
            
            print("\nFinal Report:")
            print(text[:2000] if len(text) > 2000 else text)
            
            return {"success": True, "report": text}
        else:
            return {"success": False, "error": "No result from agent"}
            
    except Exception as e:
        print(f"\nError: {e}")
        return {"success": False, "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare curriculum using skill-based workflow"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Only process first N standards (for testing)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed SDK output",
    )
    args = parser.parse_args()

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    result = asyncio.run(run_prepare_curriculum(
        limit=args.limit,
        verbose=args.verbose,
    ))

    if result.get("success"):
        print("\n✓ Curriculum preparation complete")
        return 0
    else:
        print(f"\n✗ Failed: {result.get('error', 'Unknown error')}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
