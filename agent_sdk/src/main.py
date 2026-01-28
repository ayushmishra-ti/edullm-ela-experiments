"""
FastAPI endpoint for Agentic MCQ Generation (Cloud Run).

Exposes agentic generation + self-assessment + regeneration as HTTP API.
Compatible with InceptBench Generator API Interface.

This is the AGENTIC approach - Claude autonomously decides when to:
1. Look up curriculum data
2. Populate missing curriculum data  
3. Generate questions with proper context
4. Self-assess and regenerate if below threshold

CLI Testing:
  python src/main.py --test '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'
  python src/main.py --serve  # Start server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

# Load .env if exists (optional dependency in local envs)
ROOT = Path(__file__).resolve().parents[1]
if (ROOT / ".env").exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass

# Add src to path
import sys
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import anthropic
from agentic_pipeline import generate_one_agentic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
CURRICULUM_PATH = ROOT / ".claude" / "skills" / "ela-question-generation" / "references" / "curriculum.md"
SCRIPTS_DIR = ROOT / ".claude" / "skills" / "ela-question-generation" / "scripts"
SELF_CORRECTION_SKILL_PATH = ROOT / ".claude" / "skills" / "question-self-correction" / "SKILL.md"

# Config
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
SELF_ASSESS_THRESHOLD = float(os.getenv("SELF_ASSESS_THRESHOLD", "0.85"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "1"))

app = FastAPI(title="InceptAgentic Skill MCQ Generator API")


def _utc_ts() -> str:
    """RFC3339-ish UTC timestamp with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _normalize_content_for_type(content: dict, qtype: str) -> dict:
    """
    Normalize content for specific question types without changing the outer API schema.

    - Fill-in: MUST NOT include answer_options. If an answer key like "A"/"B" is present,
      map it to the option text before removing answer_options.
    - MSQ: Ensure `answer` is a list (e.g., ["A","C"]) not a string.
    """
    def _normalize_answer_options(opts: object) -> list[dict]:
        """
        Ensure answer_options is a clean list of unique key/text dicts.
        This is a schema integrity guard (not content shaping).
        """
        if not isinstance(opts, list):
            return []

        out: list[dict] = []
        seen: set[str] = set()
        for o in opts:
            if not isinstance(o, dict):
                continue
            k = str(o.get("key", "")).strip().upper()
            t = str(o.get("text", "")).strip()
            if not k or not t:
                continue
            # Only keep the first occurrence of a key (drop duplicates)
            if k in seen:
                continue
            out.append({"key": k, "text": t})
            seen.add(k)
        return out

    q = (qtype or "").strip().lower()
    if q in {"fill-in", "fill_in", "fillin", "fill"}:
        out = dict(content or {})
        opts = out.get("answer_options")
        ans = out.get("answer")
        if isinstance(opts, list) and isinstance(ans, str):
            for o in opts:
                if str(o.get("key", "")).strip() == ans.strip():
                    out["answer"] = str(o.get("text", "")).strip()
                    break
        out.pop("answer_options", None)
        return out

    if q in {"msq", "multi-select", "multi_select", "multiselect"}:
        out = dict(content or {})
        # Clean answer_options (dedupe keys, trim text)
        if "answer_options" in out:
            out["answer_options"] = _normalize_answer_options(out.get("answer_options"))
        ans = out.get("answer")
        parts: list[str] = []
        if isinstance(ans, str):
            parts = [ans]
        elif isinstance(ans, list):
            parts = [str(a) for a in ans if str(a).strip()]

        # Handle common model output variants:
        # - ["B,D"]  -> ["B", "D"]
        # - "B, D"   -> ["B", "D"]
        # - ["B", "D"] stays as-is
        flattened: list[str] = []
        for p in parts:
            if not p:
                continue
            for token in p.split(","):
                t = token.strip()
                if t:
                    flattened.append(t)

        # De-duplicate while preserving order
        seen: set[str] = set()
        normalized: list[str] = []
        for t in flattened:
            if t in seen:
                continue
            seen.add(t)
            normalized.append(t)

        out["answer"] = normalized
        return out

    # Default (MCQ / other): clean answer_options if present
    out = dict(content or {})
    if "answer_options" in out:
        out["answer_options"] = _normalize_answer_options(out.get("answer_options"))
    return out

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class Skills(BaseModel):
    lesson_title: str | None = None
    substandard_id: str
    substandard_description: str | None = None


class GenerateRequest(BaseModel):
    grade: str = "3"
    subject: str = "ela"
    type: str = "mcq"
    difficulty: str = "medium"
    locale: str = "en-US"
    skills: Skills
    curriculum: str = "common core"
    instruction: str | None = None
    # Optional metadata some callers include (should not cause 422)
    substandard_metadata: dict | None = None


class GeneratedContent(BaseModel):
    id: str
    request: dict
    # Must support MCQ / MSQ / Fill-in content without changing schema.
    # We keep it as a plain object to avoid response_model validation errors.
    content: dict


class GeneratedContentWrapper(BaseModel):
    generated_content: list[GeneratedContent]


class GenerateResponse(BaseModel):
    """
    Matches the expected wrapper format:
    {
      "error": null,
      "success": true,
      "timestamp": "...",
      "generatedContent": { "generated_content": [ ... ] }
    }
    """

    model_config = ConfigDict(populate_by_name=True)

    error: str | None = None
    success: bool = True
    timestamp: str
    generatedContent: GeneratedContentWrapper = Field(..., alias="generatedContent")


class InceptBenchGenerateResponse(BaseModel):
    """
    Minimal InceptBench generator output.
    Some evaluator setups validate strictly and will fail if extra top-level fields exist.
    """

    generated_content: list[GeneratedContent]


# ============================================================================
# Self-Assessment Logic
# ============================================================================

SELF_ASSESSMENT_PROMPT = """
Evaluate this generated question using InceptBench criteria.
Score each dimension 0.0-1.0:

1. **factual_accuracy** - Is the answer correct? Is the explanation accurate?
2. **clarity_precision** - Is the question clear and unambiguous?
3. **distractor_quality** - Are wrong options plausible but clearly wrong? (MCQ/MSQ only)
4. **curriculum_alignment** - Does it match the standard and grade level?
5. **difficulty_alignment** - Does complexity match the stated difficulty?
6. **educational_accuracy** - Grade-appropriate? No answer giveaways?

Return ONLY JSON:
```json
{"self_assessment": {
  "overall_score": 0.85,
  "confident": true,
  "issues": []
}}
```

Be honest and critical. If unsure, set confident=false.
"""


async def self_assess_question(question: dict, request: dict) -> dict:
    """Self-assess a generated question using Claude."""
    if not ANTHROPIC_API_KEY:
        return {"overall_score": 0.85, "confident": True, "issues": []}
    
    prompt = f"""Evaluate this generated question:

QUESTION:
{json.dumps(question, indent=2)}

REQUEST:
{json.dumps(request, indent=2)}

{SELF_ASSESSMENT_PROMPT}
"""

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        
        result_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                result_text += block.text
        
        # Parse self-assessment JSON
        for block in re.findall(r'```json\s*([\s\S]*?)```', result_text):
            try:
                parsed = json.loads(block.strip())
                if "self_assessment" in parsed:
                    return parsed.get("self_assessment", {})
            except json.JSONDecodeError:
                continue
        
        # Try direct pattern
        match = re.search(r'\{[\s\S]*"self_assessment"[\s\S]*\}', result_text)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed.get("self_assessment", {})
            except json.JSONDecodeError:
                pass
        
        return {"overall_score": 0.85, "confident": True, "issues": []}
        
    except Exception as e:
        logger.warning(f"Self-assessment failed: {e}")
        return {"overall_score": 0.85, "confident": True, "issues": [], "error": str(e)}


async def regenerate_question(request: dict, original: dict, self_assessment: dict) -> dict | None:
    """Regenerate a question based on self-assessment feedback."""
    if not ANTHROPIC_API_KEY:
        return None
    
    issues = self_assessment.get("issues", [])
    score = self_assessment.get("overall_score", 0)
    
    question_type = request.get("type", "mcq")
    item_id = original.get("id", "unknown")
    
    prompt = f"""Your previous question scored {score * 100:.0f}% on self-assessment.

ORIGINAL QUESTION:
{json.dumps(original, indent=2)}

ISSUES:
{json.dumps(issues, indent=2) if issues else "Low score"}

REQUEST:
{json.dumps(request, indent=2)}

Generate an IMPROVED version that addresses the issues.
Return ONLY the question JSON:

```json
{{
  "id": "{item_id}_v2",
  "content": {{...}}
}}
```
"""

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        
        # Load self-correction skill if available
        system_prompt = ""
        if SELF_CORRECTION_SKILL_PATH.exists():
            system_prompt = SELF_CORRECTION_SKILL_PATH.read_text(encoding="utf-8")
        
        response = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_prompt if system_prompt else "You are an expert educational content creator.",
            messages=[{"role": "user", "content": prompt}],
        )
        
        result_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                result_text += block.text
        
        # Parse question JSON
        for block in re.findall(r'```json\s*([\s\S]*?)```', result_text):
            try:
                parsed = json.loads(block.strip())
                if "id" in parsed and "content" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
        
        # Try direct pattern
        match = re.search(r'\{[\s\S]*"id"[\s\S]*"content"[\s\S]*\}', result_text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
        
    except Exception as e:
        logger.warning(f"Regeneration failed: {e}")
        return None


# ============================================================================
# Core Generation Function
# ============================================================================

async def generate_with_self_correction(
    request: dict,
    threshold: float = SELF_ASSESS_THRESHOLD,
    max_retries: int = MAX_RETRIES,
    verbose: bool = False,
) -> dict:
    """
    Generate question with agentic pipeline + self-assessment + regeneration.
    
    Returns:
        dict with generated_content in InceptBench format
    """
    # Step 1: Generate using agentic pipeline
    if verbose:
        logger.info(f"Generating for {request.get('skills', {}).get('substandard_id', 'unknown')}")
    
    result = await generate_one_agentic(
        request,
        curriculum_path=CURRICULUM_PATH,
        scripts_dir=SCRIPTS_DIR,
        verbose=verbose,
    )
    
    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error", "Generation failed"),
            "generated_content": [],
        }
    
    # Extract generated item
    items = result.get("generatedContent", {}).get("generated_content", [])
    if not items:
        return {
            "success": False,
            "error": "No content generated",
            "generated_content": [],
        }
    
    item = items[0]
    question = {"id": item.get("id", ""), "content": item.get("content", {})}
    tools_used = result.get("tools_used", [])
    
    if verbose:
        tool_names = [t.get("name") for t in tools_used]
        logger.info(f"Generated (tools: {' → '.join(tool_names) if tool_names else 'none'})")
    
    # Step 2: Self-assess
    self_assessment = await self_assess_question(question, request)
    score = self_assessment.get("overall_score", 0.85)
    confident = self_assessment.get("confident", True)
    
    if verbose:
        logger.info(f"Self-assessment: {score * 100:.1f}% {'(confident)' if confident else '(not confident)'}")
    
    # Step 3: Regenerate if below threshold
    if score < threshold and max_retries > 0:
        if verbose:
            issues = self_assessment.get("issues", [])
            logger.info(f"Below threshold, regenerating... Issues: {issues}")
        
        regenerated = await regenerate_question(request, question, self_assessment)
        if regenerated:
            question = regenerated
            if verbose:
                logger.info("Regeneration successful")
    
    # Build response
    return {
        "success": True,
        "generated_content": [{
            "id": question.get("id", ""),
            "curriculum": "common_core",
            "request": request,
            "content": question.get("content", {}),
        }],
        "self_assessment": self_assessment,
        "tools_used": tools_used,
    }


# ============================================================================
# FastAPI Endpoints
# ============================================================================

@app.get("/")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "inceptagentic-skill-mcq",
        "threshold": SELF_ASSESS_THRESHOLD,
        "max_retries": MAX_RETRIES,
    }


@app.post("/generate", response_model=InceptBenchGenerateResponse)
async def generate_question(request: GenerateRequest) -> InceptBenchGenerateResponse:
    """
    Generate question using agentic approach + self-assessment + regeneration.
    
    Claude autonomously decides when to call curriculum tools.
    Compatible with InceptBench Generator API Interface.
    """
    logger.info(f"Received request: {request.skills.substandard_id}, difficulty={request.difficulty}, type={request.type}")

    # Convert to internal request format
    internal_request = {
        "type": request.type,
        "grade": request.grade,
        "skills": {
            "lesson_title": request.skills.lesson_title or "",
            "substandard_id": request.skills.substandard_id,
            "substandard_description": request.skills.substandard_description or "",
        },
        "subject": request.subject,
        "curriculum": request.curriculum,
        "difficulty": request.difficulty,
        "locale": request.locale,
    }
    if request.instruction is not None:
        internal_request["instruction"] = request.instruction
    if request.substandard_metadata is not None:
        internal_request["substandard_metadata"] = request.substandard_metadata

    try:
        # Call generation with self-correction
        result = await generate_with_self_correction(
            internal_request,
            threshold=SELF_ASSESS_THRESHOLD,
            max_retries=MAX_RETRIES,
            verbose=True,
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Generation failed: {error}")
            raise HTTPException(status_code=500, detail=error)

        # Convert to response format
        generated_content_list = []
        for item in result.get("generated_content", []):
            content_dict = _normalize_content_for_type(item.get("content", {}) or {}, request.type)

            generated_content_list.append(
                GeneratedContent(
                    id=item.get("id", ""),
                    request=internal_request,
                    content=content_dict,
                )
            )

        # Return minimal InceptBench shape:
        # { generated_content: [...] }
        return InceptBenchGenerateResponse(generated_content=generated_content_list)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============================================================================
# CLI Mode
# ============================================================================

async def cli_test(request_json: str, verbose: bool = True) -> None:
    """Test generation from CLI."""
    try:
        data = json.loads(request_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        return
    
    # Build request with defaults
    request = {
        "type": data.get("type", "mcq"),
        "grade": data.get("grade", "3"),
        "subject": data.get("subject", "ela"),
        "difficulty": data.get("difficulty", "medium"),
        "locale": data.get("locale", "en-US"),
        "curriculum": data.get("curriculum", "common_core"),
        "skills": {
            "lesson_title": data.get("skills", {}).get("lesson_title", "") or data.get("lesson_title", ""),
            "substandard_id": data.get("skills", {}).get("substandard_id", "") or data.get("substandard_id", ""),
            "substandard_description": data.get("skills", {}).get("substandard_description", "") or data.get("substandard_description", ""),
        },
    }
    
    print("=" * 60)
    print("CLI Test: Generate with Self-Correction")
    print("=" * 60)
    print(f"Standard: {request['skills']['substandard_id']}")
    print(f"Type: {request['type']}, Difficulty: {request['difficulty']}")
    print(f"Threshold: {SELF_ASSESS_THRESHOLD * 100}%, Max retries: {MAX_RETRIES}")
    print()
    
    result = await generate_with_self_correction(
        request,
        threshold=SELF_ASSESS_THRESHOLD,
        max_retries=MAX_RETRIES,
        verbose=verbose,
    )
    
    if result.get("success"):
        print("\n" + "=" * 60)
        print("Generated Content (InceptBench format)")
        print("=" * 60)
        output = {"generated_content": result.get("generated_content", [])}
        print(json.dumps(output, indent=2))
        
        # Show self-assessment
        self_assessment = result.get("self_assessment", {})
        if self_assessment:
            print("\n" + "-" * 40)
            print("Self-Assessment (internal)")
            print("-" * 40)
            print(json.dumps(self_assessment, indent=2))
    else:
        print(f"\nError: {result.get('error', 'Unknown')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentic MCQ Generator API")
    parser.add_argument(
        "--serve", "-s",
        action="store_true",
        help="Start the FastAPI server",
    )
    parser.add_argument(
        "--test", "-t",
        type=str,
        help='Test with JSON request, e.g., \'{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}\'',
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("PORT", 8080)),
        help="Port to run server on (default: 8080)",
    )
    args = parser.parse_args()
    
    if args.test:
        asyncio.run(cli_test(args.test))
    elif args.serve:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        # Default: show help
        parser.print_help()
        print("\nExamples:")
        print('  python src/main.py --test \'{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}\'')
        print('  python src/main.py --test \'{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A", "type": "msq", "difficulty": "hard"}\'')
        print("  python src/main.py --serve")
        print("  python src/main.py --serve --port 8000")
