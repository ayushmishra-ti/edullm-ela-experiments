#!/usr/bin/env python3
"""
Test script for Option C: Claude Agent SDK pipeline.

This script tests the curriculum lookup and MCQ generation using the Agent SDK.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add ccapi root to path so option_c_agent_sdk can be imported
CCAPI_ROOT = Path(__file__).resolve().parents[2]  # ccapi/
if str(CCAPI_ROOT) not in sys.path:
    sys.path.insert(0, str(CCAPI_ROOT))

from option_c_agent_sdk import (
    generate_one_agent_sdk,
    lookup_curriculum,
    save_mcq_result,
    save_curriculum_lookup,
)


async def test_curriculum_lookup():
    """Test the curriculum lookup function."""
    print("Testing curriculum lookup...")
    
    # Test with a known standard
    substandard_id = "CCSS.ELA-LITERACY.L.3.1.A"
    curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    result = lookup_curriculum(substandard_id, curriculum_path)
    print(f"\nLookup result for {substandard_id}:")
    print(json.dumps(result, indent=2))
    
    if result.get("found"):
        print("\n✓ Curriculum lookup successful!")
        if result.get("assessment_boundaries"):
            print(f"  Assessment Boundaries: {result['assessment_boundaries'][:100]}...")
        if result.get("common_misconceptions"):
            print(f"  Common Misconceptions: {len(result['common_misconceptions'])} found")
        
        # Save to outputs folder
        output_file = save_curriculum_lookup(result, substandard_id)
        print(f"\n✓ Saved to: {output_file}")
    else:
        print(f"\n✗ Standard not found: {result.get('error', 'Unknown error')}")


async def test_mcq_generation():
    """Test MCQ generation using Agent SDK."""
    print("\n" + "="*60)
    print("Testing MCQ generation with Agent SDK...")
    print("="*60)
    
    request = {
        "type": "mcq",
        "grade": "3",
        "skills": {
            "lesson_title": "",
            "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
            "substandard_description": "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences.",
        },
        "subject": "ela",
        "curriculum": "common core",
        "difficulty": "easy",
    }
    
    curriculum_path = Path(__file__).parent.parent / "data" / "curriculum.md"
    
    print(f"\nRequest: {json.dumps(request, indent=2)}")
    print("\nGenerating MCQ...")
    
    try:
        result = await generate_one_agent_sdk(request, curriculum_path=curriculum_path)
        
        print(f"\nGeneration result:")
        print(f"  Success: {result.get('success')}")
        print(f"  Mode: {result.get('generation_mode')}")
        
        if result.get("error"):
            print(f"  Error: {result['error']}")
        
        if result.get("success"):
            items = result.get("generatedContent", {}).get("generated_content", [])
            if items:
                item = items[0]
                print(f"\n✓ Generated MCQ:")
                print(f"  ID: {item.get('id')}")
                content = item.get("content", {})
                print(f"  Question: {content.get('question', '')[:100]}...")
                print(f"  Answer: {content.get('answer')}")
                print(f"  Options: {len(content.get('answer_options', []))}")
                
                # Save to outputs folder
                output_file = save_mcq_result(result, request)
                print(f"\n✓ Saved to: {output_file}")
            else:
                print("\n✗ No items generated")
        else:
            print(f"\n✗ Generation failed: {result.get('error')}")
    finally:
        # Force a loop checkpoint to let pending async cleanups finish
        await asyncio.sleep(0)


async def main():
    """Run all tests."""
    print("="*60)
    print("Option C: Claude Agent SDK - Test Suite")
    print("="*60)
    
    # Test 1: Curriculum lookup
    await test_curriculum_lookup()
    
    # Test 2: MCQ generation (requires API key)
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        await test_mcq_generation()
    else:
        print("\n" + "="*60)
        print("Skipping MCQ generation test (ANTHROPIC_API_KEY not set)")
        print("="*60)


if __name__ == "__main__":
    # Use anyio.run() instead of asyncio.run() since Claude Agent SDK uses anyio internally
    # This aligns event-loop ownership and removes the cancel-scope error
    try:
        import anyio
        anyio.run(main)
    except ImportError:
        # Fallback to asyncio if anyio is not available
        asyncio.run(main())
