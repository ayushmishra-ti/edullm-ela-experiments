#!/usr/bin/env python3
"""
Generate Passage Script for Agent Skills.

Usage:
    python scripts/generate_passage.py "<standard_id>" "<grade>" "<style>"

Example:
    python scripts/generate_passage.py "CCSS.ELA-LITERACY.RL.3.1" "3" "narrative"

Generates a grade-appropriate reading passage for the given standard.
"""

import json
import sys
from pathlib import Path

# Grade-level readability guidelines
GRADE_CONFIG = {
    "K": {"age": "5-6", "words": "50-100", "fk_grade": "0-1", "sentence": "Very short (3-6 words)"},
    "1": {"age": "6-7", "words": "75-150", "fk_grade": "1-2", "sentence": "Short (5-8 words)"},
    "2": {"age": "7-8", "words": "100-200", "fk_grade": "2-3", "sentence": "Simple sentences"},
    "3": {"age": "8-9", "words": "150-250", "fk_grade": "3-4", "sentence": "Simple/compound"},
    "4": {"age": "9-10", "words": "200-300", "fk_grade": "4-5", "sentence": "Mix of structures"},
    "5": {"age": "10-11", "words": "250-350", "fk_grade": "5-6", "sentence": "Varied structures"},
    "6": {"age": "11-12", "words": "300-400", "fk_grade": "6-7", "sentence": "Complex allowed"},
    "7": {"age": "12-13", "words": "350-450", "fk_grade": "7-8", "sentence": "Complex sentences"},
    "8": {"age": "13-14", "words": "400-500", "fk_grade": "8-9", "sentence": "Varied complexity"},
    "9": {"age": "14-15", "words": "450-550", "fk_grade": "9-10", "sentence": "Sophisticated"},
    "10": {"age": "15-16", "words": "500-600", "fk_grade": "10-11", "sentence": "Sophisticated"},
    "11": {"age": "16-17", "words": "550-650", "fk_grade": "11-12", "sentence": "Advanced"},
    "12": {"age": "17-18", "words": "600-700", "fk_grade": "12+", "sentence": "Advanced"},
}


def requires_passage(standard_id: str) -> bool:
    """Check if standard requires a passage."""
    return "RL." in standard_id or "RI." in standard_id


def get_passage_style(standard_id: str) -> str:
    """Determine passage style from standard."""
    if "RL." in standard_id:
        return "narrative"
    elif "RI." in standard_id:
        return "informational"
    return "none"


def get_cache_path(standard_id: str) -> Path:
    """Get cache file path for passage."""
    cache_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "passages"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_id = standard_id.replace(".", "_").replace(":", "_").replace("/", "_")
    return cache_dir / f"{safe_id}.json"


def lookup_cached_passage(standard_id: str) -> dict | None:
    """Look up cached passage."""
    cache_file = get_cache_path(standard_id)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except:
            return None
    return None


def save_passage_to_cache(standard_id: str, passage_data: dict) -> bool:
    """Save passage to cache."""
    cache_file = get_cache_path(standard_id)
    try:
        cache_file.write_text(json.dumps(passage_data, indent=2), encoding="utf-8")
        return True
    except:
        return False


def generate_passage_prompt(standard_id: str, grade: str, style: str) -> str:
    """Generate prompt for Claude to create passage."""
    config = GRADE_CONFIG.get(grade, GRADE_CONFIG["3"])
    
    if style == "narrative":
        passage_type = "story, fable, folktale, or myth"
    else:
        passage_type = "informational text or article"
    
    return f"""Generate a grade {grade}-appropriate {passage_type} for reading comprehension.

Standard: {standard_id}
Grade: {grade} (ages {config['age']})
Style: {style}

Requirements:
- Length: {config['words']} words
- Readability: Flesch-Kincaid Grade Level {config['fk_grade']}
- Sentence structure: {config['sentence']}
- Content: Must allow testing reading comprehension
- Vocabulary: Grade {grade}-appropriate for ages {config['age']}

The passage should be:
- Engaging and age-appropriate
- Rich enough to create comprehension questions
- Clear and well-structured

Return ONLY the passage text, no explanations or metadata."""


def main():
    if len(sys.argv) < 4:
        print(json.dumps({
            "error": "Usage: python generate_passage.py <standard_id> <grade> <style>",
            "example": 'python generate_passage.py "CCSS.ELA-LITERACY.RL.3.1" "3" "narrative"',
            "styles": ["narrative", "informational"],
        }, indent=2))
        sys.exit(1)
    
    standard_id = sys.argv[1]
    grade = sys.argv[2]
    style = sys.argv[3]
    
    # Check if passage is needed
    if not requires_passage(standard_id):
        print(json.dumps({
            "needed": False,
            "standard_id": standard_id,
            "message": "This standard does not require a passage (not RL.* or RI.*)"
        }, indent=2))
        sys.exit(0)
    
    # Check cache first
    cached = lookup_cached_passage(standard_id)
    if cached:
        print(json.dumps({
            "source": "cache",
            "passage": cached,
        }, indent=2))
        sys.exit(0)
    
    # Generate prompt for Claude
    prompt = generate_passage_prompt(standard_id, grade, style)
    config = GRADE_CONFIG.get(grade, GRADE_CONFIG["3"])
    
    result = {
        "action": "generate_passage",
        "standard_id": standard_id,
        "grade": grade,
        "style": style,
        "config": config,
        "prompt": prompt,
        "instructions": f"""
To complete this action:
1. Generate a {style} passage following the requirements above
2. Return ONLY the passage text
3. The passage will be cached for future use

Guidelines for grade {grade}:
- Target age: {config['age']} years old
- Word count: {config['words']}
- Flesch-Kincaid Grade Level: {config['fk_grade']}
- Sentence structure: {config['sentence']}
""",
        "cache_path": str(get_cache_path(standard_id)),
    }
    
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
