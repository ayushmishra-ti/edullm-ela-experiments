"""
FastAPI endpoint for Agentic MCQ Generation (Cloud Run).

Exposes agentic_pipeline.generate_one_agentic as HTTP API.
Compatible with InceptBench Generator API Interface.

This is the AGENTIC approach - Claude autonomously decides when to:
1. Look up curriculum data
2. Populate missing curriculum data  
3. Generate MCQs with proper context
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env if exists
ROOT = Path(__file__).resolve().parents[1]
if (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env", override=False)

# Add src to path
import sys
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agentic_pipeline import generate_one_agentic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="InceptAgentic Skill MCQ Generator API")

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


class AnswerOption(BaseModel):
    key: str
    text: str


class MCQContent(BaseModel):
    question: str
    answer: str
    answer_explanation: str
    answer_options: list[AnswerOption]
    image_url: list[str] = []
    additional_details: str | None = None


class GeneratedContent(BaseModel):
    id: str
    request: dict
    content: MCQContent


class GenerateResponse(BaseModel):
    generated_content: list[GeneratedContent]


@app.get("/")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "inceptagentic-skill-mcq"}


@app.post("/generate", response_model=GenerateResponse)
async def generate_question(request: GenerateRequest) -> GenerateResponse:
    """
    Generate MCQ question using agentic approach.
    
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

    try:
        # Call agentic pipeline
        result = await generate_one_agentic(
            internal_request,
            curriculum_path=ROOT / "data" / "curriculum.md",
            scripts_dir=ROOT / ".claude" / "skills" / "ela-mcq-pipeline" / "scripts",
            verbose=False,  # Reduce logging in cloud
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Generation failed: {error}")
            raise HTTPException(status_code=500, detail=error)

        # Convert to response format
        generated_content_list = []
        for item in result.get("generatedContent", {}).get("generated_content", []):
            content_dict = item.get("content", {})
            
            # Convert answer_options to list format
            answer_options = []
            opts = content_dict.get("answer_options", [])
            if isinstance(opts, list):
                answer_options = [AnswerOption(key=o.get("key", ""), text=o.get("text", "")) for o in opts]
            elif isinstance(opts, dict):
                answer_options = [AnswerOption(key=k, text=v) for k, v in opts.items()]

            mcq_content = MCQContent(
                question=content_dict.get("question", ""),
                answer=content_dict.get("answer", ""),
                answer_explanation=content_dict.get("answer_explanation", ""),
                answer_options=answer_options,
                image_url=content_dict.get("image_url", []),
                additional_details=content_dict.get("additional_details", ""),
            )

            generated_content_list.append(
                GeneratedContent(
                    id=item.get("id", ""),
                    request=internal_request,
                    content=mcq_content,
                )
            )

        return GenerateResponse(generated_content=generated_content_list)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
