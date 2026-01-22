#!/usr/bin/env python3
"""
Test script to inspect Skills API response structure and debug empty responses.

Usage:
  python scripts/test_skills_api_response.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

from ccapi.config import ANTHROPIC_API_KEY, CCAPI_ELA_MCQ_SKILL_ID


async def test_one() -> None:
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    
    if not CCAPI_ELA_MCQ_SKILL_ID:
        print("CCAPI_ELA_MCQ_SKILL_ID not set. Using Skills API requires uploaded skill.", file=sys.stderr)
        sys.exit(1)

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    request = {
        "type": "mcq",
        "grade": "3",
        "skills": {
            "lesson_title": "",
            "substandard_id": "CCSS.ELA-LITERACY.L.3.1.A",
            "substandard_description": "Explain the function of nouns, pronouns, verbs, adjectives, and adverbs in general and their functions in particular sentences."
        },
        "subject": "ela",
        "curriculum": "common core",
        "difficulty": "easy"
    }

    print("Calling Skills API...")
    user_content = f"""Generate the MCQ question for this request. Return the JSON directly in your response (not in a file).

{json.dumps(request, indent=2)}"""
    
    resp = await client.beta.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        betas=["code-execution-2025-08-25", "skills-2025-10-02"],
        container={
            "skills": [{"type": "custom", "skill_id": CCAPI_ELA_MCQ_SKILL_ID, "version": "latest"}],
        },
        messages=[{"role": "user", "content": user_content}],
        tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    )

    print(f"\nstop_reason: {getattr(resp, 'stop_reason', None)}")
    print(f"content length: {len(resp.content) if resp.content else 0}")
    print(f"\nContent blocks:")
    for i, block in enumerate(resp.content or []):
        block_type = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        print(f"  Block {i}: type={block_type}")
        if block_type == "text":
            txt = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
            print(f"    text length: {len(txt) if txt else 0}")
            if txt:
                print(f"    text preview: {txt[:200]}...")
        elif block_type == "tool_use":
            tool_id = getattr(block, "id", None) or (block.get("id") if isinstance(block, dict) else None)
            name = getattr(block, "name", None) or (block.get("name") if isinstance(block, dict) else None)
            print(f"    tool_use: id={tool_id}, name={name}")
        elif block_type == "tool_result" or block_type in ("text_editor_code_execution_tool_result", "bash_code_execution_tool_result"):
            tool_use_id = getattr(block, "tool_use_id", None) or (block.get("tool_use_id") if isinstance(block, dict) else None)
            result_content = getattr(block, "content", None) or (block.get("content") if isinstance(block, dict) else None)
            print(f"    tool_result: tool_use_id={tool_use_id}, type={block_type}")
            if isinstance(result_content, list):
                print(f"      nested content blocks: {len(result_content)}")
                for j, nested in enumerate(result_content):
                    nested_type = getattr(nested, "type", None) or (nested.get("type") if isinstance(nested, dict) else None)
                    print(f"        nested[{j}]: type={nested_type}")
                    if nested_type == "text":
                        nested_txt = getattr(nested, "text", None) or (nested.get("text") if isinstance(nested, dict) else "")
                        if nested_txt:
                            print(f"          text length: {len(nested_txt)}")
                            print(f"          text preview: {nested_txt[:500]}...")
                    elif nested_type == "text_delta":
                        delta_txt = getattr(nested, "text", None) or (nested.get("text") if isinstance(nested, dict) else "")
                        if delta_txt:
                            print(f"          delta: {delta_txt[:200]}...")
            elif isinstance(result_content, str):
                print(f"      content (string) length: {len(result_content)}")
                print(f"      full content:\n{result_content}")
            else:
                print(f"      content type: {type(result_content)}")
                print(f"      content: {result_content}")

    # Try to extract text
    parts = []
    for block in resp.content or []:
        t = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
        if t == "text":
            txt = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
            if txt:
                parts.append(txt)
        elif t == "tool_result" or t in ("text_editor_code_execution_tool_result", "bash_code_execution_tool_result"):
            result_content = getattr(block, "content", None) or (block.get("content") if isinstance(block, dict) else None)
            if isinstance(result_content, list):
                for nested in result_content:
                    nt = getattr(nested, "type", None) or (nested.get("type") if isinstance(nested, dict) else None)
                    if nt == "text" or nt == "text_delta":
                        nested_txt = getattr(nested, "text", None) or (nested.get("text") if isinstance(nested, dict) else "")
                        if nested_txt:
                            parts.append(nested_txt)
            elif isinstance(result_content, str):
                parts.append(result_content)
    
    raw = "\n".join(parts)
    print(f"\nExtracted text length: {len(raw)}")
    if raw:
        print(f"\n=== Full extracted text ===")
        print(raw)
        print(f"\n=== End of extracted text ===\n")
        # Check if JSON is in the text (look for JSON object with id and content)
        import re
        # Look for JSON in code fences or plain
        json_patterns = [
            r'```(?:json)?\s*(\{[\s\S]*?"id"[\s\S]*?"content"[\s\S]*?\})\s*```',
            r'(\{[\s\S]*?"id"[\s\S]*?"content"[\s\S]*?\})',
        ]
        found_json = None
        for pattern in json_patterns:
            match = re.search(pattern, raw, re.MULTILINE)
            if match:
                found_json = match.group(1) if len(match.groups()) > 0 else match.group(0)
                break
        if found_json:
            print(f"✓ Found JSON in text (length: {len(found_json)})")
            try:
                parsed = json.loads(found_json)
                print(f"✓ JSON is valid! Keys: {list(parsed.keys())}")
            except json.JSONDecodeError as e:
                print(f"✗ JSON parse failed: {e}")
        else:
            print("✗ No JSON pattern found in extracted text")
    else:
        print("WARNING: No text extracted from response!")


if __name__ == "__main__":
    asyncio.run(test_one())
