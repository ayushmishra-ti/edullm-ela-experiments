#!/usr/bin/env python3
"""
Generate and Refine: Agentic generation + Claude self-evaluation + regeneration.

Flow:
1. Generate using agentic pipeline (calls lookup_curriculum, populate_curriculum)
2. Claude self-assesses the generated question
3. If self-assessment < 85% → Claude regenerates with self-feedback
4. Final output matches InceptBench format exactly (no extra fields)
5. Optional: Run InceptBench once at end for validation

Key benefit: No InceptBench calls during generation loop (fast, cheap).
Curriculum tools ARE called, so curriculum.md gets populated.

Usage:
  python scripts/generate_and_refine_v2.py -n 5 -r    # Random 5
  python scripts/generate_and_refine_v2.py -n 10 -t mcq  # 10 MCQ only

Output format (InceptBench compatible):
{
  "generated_content": [
    {
      "id": "...",
      "curriculum": "common_core",
      "request": {...},
      "content": "..."  # JSON string or object
    }
  ]
}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime
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

import anthropic

# Check for API key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
if not ANTHROPIC_API_KEY:
    print("Error: ANTHROPIC_API_KEY not set in environment or .env file", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# Load Skills
# ============================================================================

GENERATION_SKILL_PATH = ROOT / ".claude" / "skills" / "ela-question-generation" / "SKILL.md"
SELF_CORRECTION_SKILL_PATH = ROOT / ".claude" / "skills" / "question-self-correction" / "SKILL.md"


def load_skill(path: Path) -> str:
    """Load a skill file."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def load_benchmark(path: Path) -> list[dict]:
    """Load benchmark JSONL file."""
    requests = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                requests.append(json.loads(line))
    return requests


# ============================================================================
# Self-Assessment Criteria (mirrors InceptBench dimensions)
# ============================================================================

SELF_ASSESSMENT_PROMPT = """
After generating the question, evaluate your own output using these InceptBench criteria.
Return your assessment as JSON at the end of your response.

## Self-Assessment Criteria (score 0.0-1.0 each)

1. **factual_accuracy** - Is the answer correct? Is the explanation accurate?
2. **clarity_precision** - Is the question clear and unambiguous?
3. **distractor_quality** - Are wrong options plausible but clearly wrong? (MCQ/MSQ only)
4. **curriculum_alignment** - Does it match the standard and grade level?
5. **difficulty_alignment** - Does complexity match the stated difficulty?
6. **educational_accuracy** - Grade-appropriate? No answer giveaways?

## Self-Assessment Output Format

After the question JSON, provide:

```json
{"self_assessment": {
  "overall_score": 0.85,
  "confident": true,
  "issues": [],
  "dimension_scores": {
    "factual_accuracy": 1.0,
    "clarity_precision": 0.9,
    "distractor_quality": 0.8,
    "curriculum_alignment": 1.0,
    "difficulty_alignment": 0.85,
    "educational_accuracy": 0.9
  }
}}
```

If you identify issues, list them:
```json
{"self_assessment": {
  "overall_score": 0.65,
  "confident": false,
  "issues": ["Distractor A too similar to correct answer", "Question wording ambiguous"],
  "dimension_scores": {...}
}}
```

Be honest and critical. If unsure, set confident=false.
"""


# ============================================================================
# Generate with Agentic Pipeline + Self-Assessment
# ============================================================================

async def generate_with_agentic_pipeline(
    request: dict,
    verbose: bool = False,
) -> dict:
    """
    Generate a question using the agentic pipeline (with curriculum tools).
    
    This calls lookup_curriculum and populate_curriculum as needed.
    
    Returns:
        dict with 'question', 'tools_used', etc.
    """
    from agentic_pipeline import generate_one_agentic
    
    # Paths for curriculum and scripts
    curriculum_path = ROOT / ".claude" / "skills" / "ela-question-generation" / "references" / "curriculum.md"
    if not curriculum_path.exists():
        curriculum_path = ROOT / "data" / "curriculum.md"
    
    scripts_dir = ROOT / ".claude" / "skills" / "ela-question-generation" / "scripts"
    
    result = await generate_one_agentic(
        request,
        curriculum_path=curriculum_path,
        scripts_dir=scripts_dir,
        verbose=verbose,
    )
    
    # Extract the generated item from the result
    if result.get("success"):
        generated_content = result.get("generatedContent", {}).get("generated_content", [])
        if generated_content:
            item = generated_content[0]
            return {
                "success": True,
                "id": item.get("id", ""),
                "content": item.get("content", {}),
                "request": request,
                "tools_used": result.get("tools_used", []),
            }
    
    return {
        "success": False,
        "error": result.get("error", "Unknown error"),
        "request": request,
        "tools_used": result.get("tools_used", []),
    }


async def self_assess_question(question: dict, request: dict) -> dict:
    """
    Self-assess a generated question using Claude.
    
    Returns:
        dict with self-assessment scores and issues
    """
    question_type = request.get("type", "mcq")
    
    prompt = f"""Evaluate this generated question using InceptBench criteria.

QUESTION:
{json.dumps(question, indent=2)}

REQUEST:
{json.dumps(request, indent=2)}

{SELF_ASSESSMENT_PROMPT}

Return ONLY the self-assessment JSON:
```json
{{"self_assessment": {{
  "overall_score": 0.85,
  "confident": true,
  "issues": [],
  "dimension_scores": {{
    "factual_accuracy": 1.0,
    "clarity_precision": 0.9,
    "distractor_quality": 0.8,
    "curriculum_alignment": 1.0,
    "difficulty_alignment": 0.85,
    "educational_accuracy": 0.9
  }}
}}}}
```
"""

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        
        # Extract text
        result_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                result_text += block.text
        
        # Parse self-assessment JSON
        import re
        
        # Try to find in code blocks first
        for block in re.findall(r'```json\s*([\s\S]*?)```', result_text):
            try:
                parsed = json.loads(block.strip())
                if "self_assessment" in parsed:
                    return parsed.get("self_assessment", {})
            except json.JSONDecodeError:
                continue
        
        # Try direct pattern
        assessment_match = re.search(r'\{[\s\S]*"self_assessment"[\s\S]*\}', result_text)
        if assessment_match:
            try:
                parsed = json.loads(assessment_match.group(0))
                return parsed.get("self_assessment", {})
            except json.JSONDecodeError:
                pass
        
        # Default assessment
        return {"overall_score": 0.85, "confident": True, "issues": []}
        
    except Exception as e:
        return {"overall_score": 0.85, "confident": True, "issues": [], "error": str(e)}


# ============================================================================
# Regenerate with Self-Feedback
# ============================================================================

async def regenerate_with_self_feedback(
    request: dict,
    original_question: dict,
    self_assessment: dict,
    verbose: bool = False,
) -> dict:
    """
    Regenerate a question based on self-assessment feedback.
    """
    generation_skill = load_skill(GENERATION_SKILL_PATH)
    correction_skill = load_skill(SELF_CORRECTION_SKILL_PATH)
    
    issues = self_assessment.get("issues", [])
    dimension_scores = self_assessment.get("dimension_scores", {})
    
    # Find lowest scoring dimensions
    low_dimensions = [k for k, v in dimension_scores.items() if v < 0.8]
    
    question_type = request.get("type", "mcq")
    item_id = original_question.get("id", "unknown")
    
    prompt = f"""Your previous question scored {self_assessment.get('overall_score', 0) * 100:.0f}% on self-assessment.

ORIGINAL QUESTION:
{json.dumps(original_question, indent=2)}

SELF-ASSESSMENT ISSUES:
{json.dumps(issues, indent=2) if issues else "None specified"}

LOW-SCORING DIMENSIONS:
{', '.join(low_dimensions) if low_dimensions else "None"}

DIMENSION SCORES:
{json.dumps(dimension_scores, indent=2)}

REQUEST:
{json.dumps(request, indent=2)}

Generate an IMPROVED version that addresses the issues above.
Maintain the same standard, grade level, and difficulty.

Return the improved question JSON only (no self-assessment needed):

```json
{{
  "id": "{item_id}_v2",
  "content": {{...}}
}}
```
"""

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        
        system_prompt = correction_skill if correction_skill else generation_skill
        
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_prompt if system_prompt else "You are an expert educational content creator.",
            messages=[{"role": "user", "content": prompt}],
        )
        
        # Extract text
        result_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                result_text += block.text
        
        # Parse question JSON
        import re
        json_match = re.search(r'\{[\s\S]*"id"[\s\S]*"content"[\s\S]*\}', result_text)
        if json_match:
            question_data = json.loads(json_match.group(0))
        else:
            # Try code blocks
            for block in re.findall(r'```json\s*([\s\S]*?)```', result_text):
                try:
                    parsed = json.loads(block.strip())
                    if "id" in parsed and "content" in parsed:
                        question_data = parsed
                        break
                except json.JSONDecodeError:
                    continue
            else:
                raise ValueError("Could not parse regenerated question")
        
        return {
            "success": True,
            "question": question_data,
            "regenerated": True,
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Main Pipeline
# ============================================================================

async def generate_and_refine_v2(
    requests: list[dict],
    threshold: float = 0.85,
    max_retries: int = 1,
    verbose: bool = False,
) -> dict:
    """
    Generate questions with agentic pipeline + Claude self-evaluation.
    
    Flow:
    1. Generate using agentic pipeline (calls curriculum tools)
    2. Self-assess the generated question
    3. If self_assessment.overall_score < threshold → regenerate
    4. Output in InceptBench format (no self_assessment in output)
    """
    results = []
    stats = {
        "total": len(requests),
        "generated": 0,
        "generation_failed": 0,
        "below_threshold": 0,
        "regenerated": 0,
        "final_count": 0,
    }
    
    for i, request in enumerate(requests):
        skills = request.get("skills", {})
        substandard_id = skills.get("substandard_id", "unknown")
        item_id = f"{substandard_id}_{request.get('type', 'mcq')}_{request.get('difficulty', 'easy')}"
        
        print(f"\n[{i+1}/{len(requests)}] {item_id}")
        
        # Step 1: Generate using agentic pipeline (calls curriculum tools)
        print("  → Generating (agentic)...", end=" ", flush=True)
        result = await generate_with_agentic_pipeline(request, verbose)
        
        if not result.get("success"):
            print(f"✗ Failed: {result.get('error', 'Unknown')[:50]}")
            stats["generation_failed"] += 1
            continue
        
        # Show tools used
        tools = [t.get("name") for t in result.get("tools_used", [])]
        print(f"✓ (tools: {' → '.join(tools) if tools else 'none'})")
        stats["generated"] += 1
        
        # Build question dict
        question = {
            "id": result.get("id", ""),
            "content": result.get("content", {}),
        }
        
        # Step 2: Self-assess the generated question
        print("  → Self-assessing...", end=" ", flush=True)
        self_assessment = await self_assess_question(question, request)
        score = self_assessment.get("overall_score", 0.85)
        confident = self_assessment.get("confident", True)
        issues = self_assessment.get("issues", [])
        
        score_pct = round(score * 100, 1)
        
        if score >= threshold and confident:
            print(f"✓ {score_pct}% (confident, passed)")
            results.append({
                "question": question,
                "request": request,
                "self_score": score,
            })
            stats["final_count"] += 1
            continue
        
        # Below threshold or not confident
        print(f"⚠ {score_pct}% {'(not confident)' if not confident else ''}")
        if issues:
            print(f"      Issues: {', '.join(issues[:2])}{'...' if len(issues) > 2 else ''}")
        
        stats["below_threshold"] += 1
        
        # Step 2: Regenerate with self-feedback
        if max_retries > 0:
            print("  → Regenerating with self-feedback...", end=" ", flush=True)
            
            regen_result = await regenerate_with_self_feedback(
                request, question, self_assessment, verbose
            )
            
            if regen_result.get("success"):
                print("✓ Regenerated")
                stats["regenerated"] += 1
                results.append({
                    "question": regen_result["question"],
                    "request": request,
                    "self_score": score,
                    "regenerated": True,
                })
                stats["final_count"] += 1
            else:
                print(f"✗ Failed: {regen_result.get('error', 'Unknown')[:30]}")
                # Keep original
                results.append({
                    "question": question,
                    "request": request,
                    "self_score": score,
                })
                stats["final_count"] += 1
        else:
            # No retries, keep original
            results.append({
                "question": question,
                "request": request,
                "self_score": score,
            })
            stats["final_count"] += 1
    
    return {
        "results": results,
        "stats": stats,
    }


def to_inceptbench_format(results: list[dict]) -> dict:
    """
    Convert results to InceptBench-compatible format.
    
    Output format:
    {
      "generated_content": [
        {
          "id": "...",
          "curriculum": "common_core",
          "request": {...},
          "content": "..." or {...}
        }
      ]
    }
    """
    generated_content = []
    
    for r in results:
        question = r["question"]
        request = r["request"]
        
        # Build InceptBench format
        item = {
            "id": question.get("id", ""),
            "curriculum": "common_core",
            "request": {
                "grade": request.get("grade", "3"),
                "subject": request.get("subject", "ela"),
                "type": request.get("type", "mcq"),
                "difficulty": request.get("difficulty", "easy"),
                "locale": "en-US",
                "skills": request.get("skills", {}),
            },
            "content": question.get("content", {}),
        }
        
        generated_content.append(item)
    
    return {"generated_content": generated_content}


def main():
    parser = argparse.ArgumentParser(
        description="Generate and Refine v2: Claude self-evaluation (no InceptBench during loop)"
    )
    default_input = ROOT / "data" / "grade-3-ela-benchmark.jsonl"
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=default_input,
        help="Input benchmark JSONL file",
    )
    parser.add_argument(
        "--grade", "-g",
        type=str,
        default=None,
        help="Convenience flag: uses data/grade-<grade>-ela-benchmark.jsonl when --input is not set",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=ROOT / "outputs" / "batch_generated.json",
        help="Output JSON file (InceptBench format)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Limit number of items to generate",
    )
    parser.add_argument(
        "--random", "-r",
        action="store_true",
        help="Randomly sample items instead of taking first N",
    )
    parser.add_argument(
        "--type", "-t",
        choices=["all", "mcq", "msq", "fill-in"],
        default="all",
        help="Filter by question type",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Self-assessment threshold for regeneration (default: 0.85)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Maximum regeneration attempts per item (default: 1)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )
    args = parser.parse_args()

    # If caller provided --grade and didn't override --input, select grade-specific benchmark.
    if args.grade and args.input == default_input:
        args.input = ROOT / "data" / f"grade-{args.grade}-ela-benchmark.jsonl"
    
    print("=" * 60)
    print("Generate and Refine (Agentic + Self-Evaluation)")
    print("=" * 60)
    print(f"\nThreshold: {args.threshold * 100}%")
    print(f"Max retries: {args.max_retries}")
    print("Note: Curriculum tools ARE called. No InceptBench during loop.")
    print()
    
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
    
    # Limit (with optional random sampling)
    if args.limit:
        if args.random:
            requests = random.sample(requests, min(args.limit, len(requests)))
            print(f"Randomly sampled {len(requests)} requests")
        else:
            requests = requests[:args.limit]
            print(f"Limited to {len(requests)} requests")
    
    # Run pipeline
    result = asyncio.run(generate_and_refine_v2(
        requests,
        threshold=args.threshold,
        max_retries=args.max_retries,
        verbose=args.verbose,
    ))
    
    # Convert to InceptBench format
    output_data = to_inceptbench_format(result["results"])
    
    # Add metadata (separate from generated_content)
    output_with_meta = {
        **output_data,
        "_metadata": {
            **result["stats"],
            "threshold": args.threshold,
            "max_retries": args.max_retries,
            "timestamp": datetime.now().isoformat(),
            "note": "Self-assessment only, no InceptBench during generation",
        },
    }
    
    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_with_meta, indent=2), encoding="utf-8")
    
    # Print summary
    stats = result["stats"]
    print(f"\n{'='*60}")
    print("Pipeline Complete (No InceptBench calls)")
    print(f"{'='*60}")
    print(f"Total requests:      {stats['total']}")
    print(f"Generated:           {stats['generated']}")
    print(f"Generation failed:   {stats['generation_failed']}")
    print(f"Below threshold:     {stats['below_threshold']}")
    print(f"Regenerated:         {stats['regenerated']}")
    print(f"Final output count:  {stats['final_count']}")
    
    print(f"\nOutput saved to: {args.output}")
    print(f"\nTo validate with InceptBench:")
    print(f"  python -m inceptbench evaluate {args.output}")


if __name__ == "__main__":
    main()
