#!/usr/bin/env python3
"""
Batch generate ELA questions using Agent SDK skills approach.

Usage:
  python scripts/generate_batch.py [--input PATH] [--output PATH] [--limit N] [--type TYPE]

Example:
  python scripts/generate_batch.py --limit 50 --type mcq
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parents[1]

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

# Check for API key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("Error: ANTHROPIC_API_KEY not set in environment or .env file", file=sys.stderr)
    sys.exit(1)


def load_skill() -> str:
    """Load the ela-question-generation skill as system prompt."""
    skill_path = ROOT / ".claude" / "skills" / "ela-question-generation" / "SKILL.md"
    if not skill_path.exists():
        print(f"Error: Skill file not found: {skill_path}", file=sys.stderr)
        sys.exit(1)
    
    content = skill_path.read_text(encoding="utf-8")
    # Remove YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()
    return content


def lookup_curriculum(standard_id: str) -> dict:
    """Look up curriculum data for a standard."""
    import subprocess
    
    script_path = ROOT / ".claude" / "skills" / "ela-question-generation" / "scripts" / "lookup_curriculum.py"
    if not script_path.exists():
        return {"found": False, "error": "Script not found"}
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), standard_id],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"found": False, "error": result.stderr}
    except Exception as e:
        return {"found": False, "error": str(e)}


def extract_json(text: str) -> dict | None:
    """Extract JSON from response text."""
    # Try to find JSON object
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'(\{[\s\S]*"id"[\s\S]*"content"[\s\S]*\})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    
    # Try parsing entire text as JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def generate_one(request: dict, skill_prompt: str) -> dict:
    """Generate one question using Claude API with skill prompt."""
    import anthropic
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Get curriculum context
    substandard_id = request.get("skills", {}).get("substandard_id", "")
    curriculum = lookup_curriculum(substandard_id)
    
    # Build user message
    user_message = f"""Generate a question for this request:

```json
{json.dumps(request, indent=2)}
```

"""
    
    if curriculum.get("found"):
        user_message += f"""
Curriculum Context for {substandard_id}:

Assessment Boundaries:
{curriculum.get('assessment_boundaries', 'Not specified')}

Common Misconceptions:
{json.dumps(curriculum.get('common_misconceptions', []), indent=2)}

Use these misconceptions to design effective distractors.
"""
    
    user_message += """
Return ONLY the JSON object with id, content (answer, question, image_url, answer_options, answer_explanation).
"""
    
    try:
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            max_tokens=2000,
            system=skill_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        
        # Extract text from response
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        
        # Parse JSON
        parsed = extract_json(text)
        if parsed:
            return {
                "success": True,
                "id": parsed.get("id", ""),
                "content": parsed.get("content", {}),
                "request": request,
            }
        else:
            return {
                "success": False,
                "error": "Failed to parse JSON from response",
                "raw_response": text[:500],
                "request": request,
            }
            
    except Exception as e:
        error_msg = str(e)
        # Try to extract more details from API errors
        if hasattr(e, 'response'):
            try:
                error_msg = f"{error_msg} - {e.response.text}"
            except:
                pass
        return {
            "success": False,
            "error": error_msg,
            "request": request,
        }


def load_benchmark(path: Path) -> list[dict]:
    """Load benchmark JSONL file."""
    requests = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                requests.append(json.loads(line))
    return requests


def main():
    parser = argparse.ArgumentParser(description="Batch generate ELA questions")
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=ROOT / "data" / "grade-3-ela-benchmark.jsonl",
        help="Input benchmark JSONL file",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=ROOT / "outputs" / "batch_generated.json",
        help="Output JSON file",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Limit number of items to generate",
    )
    parser.add_argument(
        "--type", "-t",
        choices=["all", "mcq", "msq", "fill-in"],
        default="all",
        help="Filter by question type",
    )
    args = parser.parse_args()
    
    # Load skill
    print("Loading skill...")
    skill_prompt = load_skill()
    
    # Show model being used
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    print(f"Using model: {model}")
    
    # Load benchmark
    print(f"Loading benchmark from: {args.input}")
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    requests = load_benchmark(args.input)
    print(f"Loaded {len(requests)} requests")
    
    # Filter by type
    if args.type != "all":
        requests = [r for r in requests if r.get("type") == args.type]
        print(f"Filtered to {len(requests)} {args.type} requests")
    
    # Limit
    if args.limit:
        requests = requests[:args.limit]
        print(f"Limited to {len(requests)} requests")
    
    # Generate
    print(f"\nGenerating {len(requests)} questions...\n")
    results = []
    success_count = 0
    
    for i, request in enumerate(requests):
        item_id = f"{request.get('skills', {}).get('substandard_id', 'unknown')}_{request.get('type', 'mcq')}_{request.get('difficulty', 'easy')}"
        print(f"  [{i+1}/{len(requests)}] {item_id}...", end=" ")
        
        result = generate_one(request, skill_prompt)
        results.append(result)
        
        if result.get("success"):
            print("✓")
            success_count += 1
        else:
            error = result.get('error', 'Unknown error')
            print(f"✗ {error[:100]}")
            # Print full error for first failure
            if success_count == 0 and len(results) == 1:
                print(f"\n    Full error: {error}\n")
    
    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "generated_content": [r for r in results if r.get("success")],
        "errors": [r for r in results if not r.get("success")],
        "metadata": {
            "total": len(requests),
            "success": success_count,
            "failed": len(requests) - success_count,
            "type_filter": args.type,
            "timestamp": datetime.now().isoformat(),
        },
    }
    
    args.output.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    
    print(f"\n{'='*60}")
    print("Generation Complete")
    print(f"{'='*60}")
    print(f"Total: {len(requests)}")
    print(f"Success: {success_count}")
    print(f"Failed: {len(requests) - success_count}")
    print(f"\nOutput saved to: {args.output}")


if __name__ == "__main__":
    main()
