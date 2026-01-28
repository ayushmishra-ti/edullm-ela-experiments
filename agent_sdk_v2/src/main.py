"""
ELA Question Generation API - Claude Agent SDK (Skills Approach)

This API uses the Claude Agent SDK with Skills for question generation.
Skills are defined in .claude/skills/ and discovered automatically by the SDK.

Endpoints:
- POST /generate              - Generate ELA questions (v1 compatible)
- POST /generate_v2           - Generate ELA questions (SDK Skills)
- GET  /                      - Health check

Architecture:
- Skills are in .claude/skills/ (ela-question-generation, generate-passage)
- SDK discovers skills automatically via setting_sources=["user", "project"]
- Claude autonomously invokes skills when relevant to the request
- Curriculum data is pre-fetched by Python (not via skill)

Reference: https://platform.claude.com/docs/en/agent-sdk/skills

CLI Testing:
  python src/main.py --serve
  python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'
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

# Project root (where .claude/skills/ lives)
ROOT = Path(__file__).resolve().parents[1]

# Load .env if exists
if (ROOT / ".env").exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass

# Add src to path for imports
import sys
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# Import SDK-based pipelines (Skills approach only)
from agentic_pipeline_sdk import generate_one_agentic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="ELA Question Generation API",
    description="Generate ELA questions using Claude Agent SDK with Skills",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
async def health_check() -> dict:
    """Health check and API info."""
    return {
        "status": "ok",
        "service": "ela-question-generation",
        "version": "2.0.0",
        "architecture": "Claude Agent SDK with Skills",
        "skills_location": str(ROOT / ".claude" / "skills"),
        "documentation": "https://platform.claude.com/docs/en/agent-sdk/skills",
        "endpoints": {
            "/generate": "POST - Generate ELA questions (v1 compatible)",
            "/generate_v2": "POST - Generate ELA questions (SDK Skills)",
        },
    }


@app.post("/generate", response_model=GenerateResponse)
@app.post("/generate_v2", response_model=GenerateResponse)
async def generate_question(request: GenerateRequest) -> GenerateResponse:
    """
    Generate an ELA question using Claude Agent SDK with Skills.
    
    The SDK:
    1. Discovers skills in .claude/skills/
    2. Claude reads the prompt and decides which skill to use
    3. Claude invokes ela-question-generation skill
    4. Returns question in SKILL.md specified format
    """
    logger.info(f"Generate: {request.skills.substandard_id}, type={request.type}")
    
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
    print("ELA Question Generation - Claude Agent SDK (Skills)")
    print("=" * 60)
    print(f"Standard: {request['skills']['substandard_id']}")
    print(f"Type: {request['type']}, Difficulty: {request['difficulty']}")
    print(f"Skills Location: {ROOT / '.claude' / 'skills'}")
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
        if result.get("raw_response"):
            print(f"Raw response: {result.get('raw_response')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ELA Question Generation API - Claude Agent SDK (Skills)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py --serve
  python src/main.py --test-generate '{"substandard_id": "CCSS.ELA-LITERACY.L.3.1.A"}'

Architecture:
  - Skills are in .claude/skills/ (ela-question-generation, generate-passage)
  - SDK discovers skills automatically
  - Claude invokes skills based on prompt content
  - Curriculum is pre-fetched by Python
  - Reference: https://platform.claude.com/docs/en/agent-sdk/skills
"""
    )
    parser.add_argument("--serve", "-s", action="store_true", help="Start the API server")
    parser.add_argument("--test-generate", type=str, help="Test question generation with JSON")
    parser.add_argument("--port", "-p", type=int, default=int(os.environ.get("PORT", 8080)))
    args = parser.parse_args()
    
    if args.test_generate:
        asyncio.run(cli_test_generate(args.test_generate))
    elif args.serve:
        import uvicorn
        print("\n" + "=" * 60)
        print("ELA Question Generation API")
        print("=" * 60)
        print("Architecture: Claude Agent SDK with Skills")
        print(f"Skills Location: {ROOT / '.claude' / 'skills'}")
        print(f"Port: {args.port}")
        print("Reference: https://platform.claude.com/docs/en/agent-sdk/skills")
        print("=" * 60 + "\n")
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        parser.print_help()
