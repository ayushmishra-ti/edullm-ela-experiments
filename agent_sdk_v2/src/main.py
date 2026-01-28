"""
FastAPI Endpoints for ELA SDK v2 (Cloud Run).

Endpoints:
- POST /generate          - Generate ELA questions (MCQ, MSQ, Fill-in)
- POST /populate-curriculum - Pre-populate curriculum data for standards
- GET  /                  - Health check

Architecture:
- Uses Claude Agent SDK with automatic skill discovery
- Skills are in .claude/skills/ and discovered automatically
- Set USE_SDK=true to use claude_agent_sdk (requires pip install claude-agent-sdk)
- Set USE_SDK=false to use fallback Anthropic API (default for now)

CLI Testing:
  python src/main.py --serve
  python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'
  python src/main.py --test-curriculum '{"standard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env if exists
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

# Select SDK mode
# USE_SDK=true: Use claude_agent_sdk (recommended, requires pip install claude-agent-sdk)
# USE_SDK=false: Use fallback Anthropic API
USE_SDK = os.getenv("USE_SDK", "false").lower() == "true"

if USE_SDK:
    try:
        from agentic_pipeline_sdk import generate_one_agentic
        SDK_MODE = "claude_agent_sdk"
    except ImportError:
        from agentic_pipeline import generate_one_agentic
        SDK_MODE = "fallback_anthropic"
else:
    from agentic_pipeline import generate_one_agentic
    SDK_MODE = "anthropic_api"

from curriculum_pipeline import populate_curriculum_for_standard, populate_curriculum_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

logger.info(f"SDK mode: {SDK_MODE}")

app = FastAPI(
    title="ELA SDK API",
    description=f"Generate ELA questions using Claude Agent SDK. Mode: {SDK_MODE}",
    version="2.0.0",
)

# Versioned router for v2 endpoints
from fastapi import APIRouter
v2_router = APIRouter(prefix="/v2", tags=["v2"])

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v2 router
app.include_router(v2_router)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ============================================================================
# Request/Response Models
# ============================================================================

class Skills(BaseModel):
    substandard_id: str
    substandard_description: str | None = None
    lesson_title: str | None = None


class GenerateRequest(BaseModel):
    grade: str = "3"
    subject: str = "ela"
    type: str = "mcq"
    difficulty: str = "medium"
    locale: str = "en-US"
    skills: Skills
    curriculum: str = "common core"
    instruction: str | None = None


class GeneratedContent(BaseModel):
    id: str
    request: dict
    content: dict


class GenerateResponse(BaseModel):
    generated_content: list[GeneratedContent]


class CurriculumRequest(BaseModel):
    standard_id: str
    standard_description: str
    grade: str = "3"
    force: bool = False


class CurriculumBatchRequest(BaseModel):
    standards: list[CurriculumRequest]
    force: bool = False


class CurriculumResponse(BaseModel):
    success: bool
    standard_id: str
    source: str | None = None
    curriculum_data: dict | None = None
    saved_to_file: bool | None = None
    error: str | None = None


class CurriculumBatchResponse(BaseModel):
    results: list[CurriculumResponse]
    stats: dict


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "ela-sdk",
        "version": "2.0.0",
        "sdk_mode": SDK_MODE,
        "sdk_description": {
            "claude_agent_sdk": "Using Claude Agent SDK with automatic skill discovery",
            "anthropic_api": "Using Anthropic API directly (fallback)",
            "fallback_anthropic": "claude_agent_sdk not installed, using Anthropic API",
        }.get(SDK_MODE, SDK_MODE),
        "endpoints": {
            "/generate": "POST - Generate ELA questions",
            "/v2/generate": "POST - Generate ELA questions (v2)",
            "/populate-curriculum": "POST - Populate curriculum for a standard",
            "/populate-curriculum/batch": "POST - Populate curriculum for multiple standards",
        },
    }


async def _generate_question_impl(request: GenerateRequest) -> GenerateResponse:
    """
    Internal implementation for question generation.
    
    Architecture:
    - Main agent reads ela-question-generation/SKILL.md
    - If RL/RI standard, spawns sub-agent for passage generation
    - Sub-agent reads generate-passage/SKILL.md
    """
    logger.info(f"Generate request: {request.skills.substandard_id}, type={request.type}")
    
    # Convert to internal format
    internal_request = {
        "type": request.type,
        "grade": request.grade,
        "subject": request.subject,
        "difficulty": request.difficulty,
        "locale": request.locale,
        "curriculum": request.curriculum,
        "skills": {
            "substandard_id": request.skills.substandard_id,
            "substandard_description": request.skills.substandard_description or "",
            "lesson_title": request.skills.lesson_title or "",
        },
    }
    if request.instruction:
        internal_request["instruction"] = request.instruction
    
    try:
        result = await generate_one_agentic(internal_request, verbose=True)
        
        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Generation failed: {error}")
            raise HTTPException(status_code=500, detail=error)
        
        # Extract generated content
        items = result.get("generatedContent", {}).get("generated_content", [])
        generated_content = []
        
        for item in items:
            generated_content.append(GeneratedContent(
                id=item.get("id", ""),
                request=internal_request,
                content=item.get("content", {}),
            ))
        
        return GenerateResponse(generated_content=generated_content)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# Expose on both /generate (backward compatible) and /v2/generate (explicit v2)
@app.post("/generate", response_model=GenerateResponse)
async def generate_question(request: GenerateRequest) -> GenerateResponse:
    """Generate ELA question (backward compatible endpoint)."""
    return await _generate_question_impl(request)


@v2_router.post("/generate", response_model=GenerateResponse)
async def generate_question_v2(request: GenerateRequest) -> GenerateResponse:
    """Generate ELA question using v2 pipeline with SKILL.md."""
    return await _generate_question_impl(request)


@app.post("/populate-curriculum", response_model=CurriculumResponse)
async def populate_curriculum(request: CurriculumRequest) -> CurriculumResponse:
    """
    Populate curriculum data for a single standard.
    
    Architecture:
    - Sub-agent reads populate-curriculum/SKILL.md
    - Generates learning objectives, assessment boundaries, misconceptions
    - Saves to curriculum.md
    """
    logger.info(f"Populate curriculum: {request.standard_id}")
    
    try:
        result = await populate_curriculum_for_standard(
            request.standard_id,
            request.standard_description,
            request.grade,
            force=request.force,
            verbose=True,
        )
        
        return CurriculumResponse(
            success=result.get("success", False),
            standard_id=result.get("standard_id", request.standard_id),
            source=result.get("source"),
            curriculum_data=result.get("curriculum_data"),
            saved_to_file=result.get("saved_to_file"),
            error=result.get("error"),
        )
        
    except Exception as e:
        logger.error(f"Curriculum error: {e}", exc_info=True)
        return CurriculumResponse(
            success=False,
            standard_id=request.standard_id,
            error=str(e),
        )


@app.post("/populate-curriculum/batch", response_model=CurriculumBatchResponse)
async def populate_curriculum_batch_endpoint(request: CurriculumBatchRequest) -> CurriculumBatchResponse:
    """
    Populate curriculum data for multiple standards.
    """
    logger.info(f"Populate curriculum batch: {len(request.standards)} standards")
    
    standards = [
        {
            "standard_id": s.standard_id,
            "standard_description": s.standard_description,
            "grade": s.grade,
        }
        for s in request.standards
    ]
    
    try:
        result = await populate_curriculum_batch(
            standards,
            force=request.force,
            verbose=True,
        )
        
        responses = []
        for r in result.get("results", []):
            responses.append(CurriculumResponse(
                success=r.get("success", False),
                standard_id=r.get("standard_id", ""),
                source=r.get("source"),
                curriculum_data=r.get("curriculum_data"),
                saved_to_file=r.get("saved_to_file"),
                error=r.get("error"),
            ))
        
        return CurriculumBatchResponse(
            results=responses,
            stats=result.get("stats", {}),
        )
        
    except Exception as e:
        logger.error(f"Batch curriculum error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ============================================================================
# CLI Mode
# ============================================================================

async def cli_test_generate(request_json: str) -> None:
    """Test generation from CLI."""
    try:
        data = json.loads(request_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        return
    
    request = {
        "type": data.get("type", "mcq"),
        "grade": data.get("grade", "3"),
        "subject": data.get("subject", "ela"),
        "difficulty": data.get("difficulty", "medium"),
        "locale": data.get("locale", "en-US"),
        "curriculum": data.get("curriculum", "common_core"),
        "skills": {
            "substandard_id": data.get("skills", {}).get("substandard_id", "") or data.get("substandard_id", ""),
            "substandard_description": data.get("skills", {}).get("substandard_description", "") or data.get("substandard_description", ""),
        },
    }
    
    print("=" * 60)
    print("CLI Test: Generate Question")
    print("=" * 60)
    print(f"Standard: {request['skills']['substandard_id']}")
    print(f"Type: {request['type']}, Difficulty: {request['difficulty']}")
    print()
    
    result = await generate_one_agentic(request, verbose=True)
    
    if result.get("success"):
        print("\n" + "=" * 60)
        print("Generated Content")
        print("=" * 60)
        output = {"generated_content": result.get("generatedContent", {}).get("generated_content", [])}
        print(json.dumps(output, indent=2))
    else:
        print(f"\nError: {result.get('error', 'Unknown')}")


async def cli_test_curriculum(request_json: str) -> None:
    """Test curriculum population from CLI."""
    try:
        data = json.loads(request_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        return
    
    standard_id = data.get("standard_id", "")
    standard_description = data.get("standard_description", "")
    grade = data.get("grade", "3")
    force = data.get("force", False)
    
    print("=" * 60)
    print("CLI Test: Populate Curriculum")
    print("=" * 60)
    print(f"Standard: {standard_id}")
    print(f"Force: {force}")
    print()
    
    result = await populate_curriculum_for_standard(
        standard_id,
        standard_description,
        grade,
        force=force,
        verbose=True,
    )
    
    print("\n" + "=" * 60)
    print("Result")
    print("=" * 60)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ELA SDK v2 API")
    parser.add_argument("--serve", "-s", action="store_true", help="Start the server")
    parser.add_argument("--test-generate", type=str, help="Test question generation")
    parser.add_argument("--test-curriculum", type=str, help="Test curriculum population")
    parser.add_argument("--port", "-p", type=int, default=int(os.environ.get("PORT", 8080)))
    parser.add_argument("--use-sdk", action="store_true", help="Use claude_agent_sdk (requires pip install)")
    args = parser.parse_args()
    
    # Override SDK mode if specified via CLI
    if args.use_sdk:
        os.environ["USE_SDK"] = "true"
        try:
            from agentic_pipeline_sdk import generate_one_agentic as gen_func
            globals()["generate_one_agentic"] = gen_func
            print("Using claude_agent_sdk")
        except ImportError:
            print("Warning: claude_agent_sdk not installed, using fallback")
    
    if args.test_generate:
        asyncio.run(cli_test_generate(args.test_generate))
    elif args.test_curriculum:
        asyncio.run(cli_test_curriculum(args.test_curriculum))
    elif args.serve:
        import uvicorn
        print(f"\nStarting server with SDK mode: {SDK_MODE}")
        print("To use Claude Agent SDK: set USE_SDK=true (requires pip install claude-agent-sdk)\n")
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("SDK MODES")
        print("=" * 60)
        print("  USE_SDK=true  : Use claude_agent_sdk (automatic skill discovery)")
        print("  USE_SDK=false : Use Anthropic API directly (default)")
        print()
        print("Examples:")
        print('  python src/main.py --serve                    # Default mode')
        print('  python src/main.py --serve --use-sdk          # Use claude_agent_sdk')
        print('  python src/main.py --test-generate \'{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}\'')
        print('  python src/main.py --test-curriculum \'{"standard_id": "CCSS.ELA-LITERACY.L.3.1.A", "standard_description": "..."}\'')
