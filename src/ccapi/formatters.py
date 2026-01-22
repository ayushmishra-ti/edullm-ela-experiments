"""Transform benchmark rows to request format and normalize generated output."""

from __future__ import annotations

import json
from typing import Any


def benchmark_row_to_request(row: dict) -> dict:
    """
    Convert a grade-3-ela-benchmark.jsonl row (type=mcq) to pipeline request format.

    Input row: { "grade", "subject", "type", "difficulty", "skills": { "substandard_id", "substandard_description" } }
    """
    skills = row.get("skills") or {}
    return {
        "type": "mcq",
        "grade": str(row.get("grade", "3")),
        "skills": {
            "lesson_title": skills.get("lesson_title", ""),
            "substandard_id": skills.get("substandard_id", ""),
            "substandard_description": skills.get("substandard_description", ""),
        },
        "subject": "ela",
        "curriculum": "common core",
        "difficulty": row.get("difficulty", "medium"),
    }


def normalize_content(content: dict) -> dict:
    """Ensure content has image_url=[] and answer_options as [{"key","text"}], etc."""
    out = dict(content)
    out["image_url"] = []
    opts = out.get("answer_options")
    if isinstance(opts, dict):
        out["answer_options"] = [{"key": k, "text": v} for k, v in opts.items()]
    elif isinstance(opts, list) and opts and isinstance(opts[0], dict):
        out["answer_options"] = [
            {"key": str(o.get("key", "")), "text": str(o.get("text", ""))} for o in opts
        ]
    return out


def parsed_to_item(parsed: dict, request: dict, normalize: bool = True) -> dict:
    """
    Build standardized item from parsed LLM JSON and original request.

    parsed: { "id", "content": { "answer", "question", "image_url", "answer_options", ... } }
    """
    c = parsed.get("content", {})
    content = normalize_content(c) if normalize else dict(c)
    return {
        "id": parsed.get("id", ""),
        "content": content,
        "request": request,
    }


def _content_to_incept_string(c: dict) -> str:
    """Build InceptBench content string: 'Question? A) opt1 B) opt2 C) opt3 D) opt4'."""
    q = (c.get("question") or "").strip()
    opts = c.get("answer_options") or []
    if not isinstance(opts, list):
        opts = []
    parts = [f"{o.get('key', '')}) {o.get('text', '')}".strip() for o in opts if isinstance(o, dict)]
    if parts:
        return f"{q} {' '.join(parts)}".strip()
    return q


def to_inceptbench_item(item: dict, *, content_as_string: bool = False) -> dict:
    """
    Convert our generated item to InceptBench generated_content entry.

    InceptBench expects: id, curriculum, request { grade, subject, type, difficulty, locale, skills, instruction }, content.
    content: string like "What is 2+2? A) 3 B) 4 C) 5 D) 6" when content_as_string=True; else the raw object.

    item: { "id", "content": { question, answer_options, ... }, "request": {...} }
    """
    req = dict(item.get("request") or {})
    req.setdefault("locale", "en-US")
    req.setdefault("instruction", "")
    c = item.get("content") or {}
    content = _content_to_incept_string(c) if content_as_string else c
    return {
        "id": item.get("id", ""),
        "curriculum": "common_core",
        "request": req,
        "content": content,
    }
