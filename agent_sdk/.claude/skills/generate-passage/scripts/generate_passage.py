#!/usr/bin/env python3
"""
Generate Passage Script.

Usage:
    python scripts/generate_passage.py "<standard_id>" "<grade>" "<style>"

Style: "narrative" (for RL.*) or "informational" (for RI.*)
"""

import json
import sys
from pathlib import Path

GRADE_CONFIG = {
    "K": {"age": "5-6", "words": "50-100", "fk": "0-1"},
    "1": {"age": "6-7", "words": "75-150", "fk": "1-2"},
    "2": {"age": "7-8", "words": "100-200", "fk": "2-3"},
    "3": {"age": "8-9", "words": "150-250", "fk": "3-4"},
    "4": {"age": "9-10", "words": "200-300", "fk": "4-5"},
    "5": {"age": "10-11", "words": "250-350", "fk": "5-6"},
    "6": {"age": "11-12", "words": "300-400", "fk": "6-7"},
    "7": {"age": "12-13", "words": "350-450", "fk": "7-8"},
    "8": {"age": "13-14", "words": "400-500", "fk": "8-9"},
    "9": {"age": "14-15", "words": "450-550", "fk": "9-10"},
    "10": {"age": "15-16", "words": "500-600", "fk": "10-11"},
    "11": {"age": "16-17", "words": "550-650", "fk": "11-12"},
    "12": {"age": "17-18", "words": "600-700", "fk": "12+"},
}


def get_cache_path(standard_id: str) -> Path:
    """Get cache file path."""
    cache_dir = Path(__file__).parent.parent.parent.parent / "data" / "passages"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_id = standard_id.replace(".", "_").replace(":", "_")
    return cache_dir / f"{safe_id}.json"


def check_cache(standard_id: str) -> dict | None:
    """Check for cached passage."""
    path = get_cache_path(standard_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def main():
    if len(sys.argv) < 4:
        print(json.dumps({
            "error": "Usage: python generate_passage.py <standard_id> <grade> <style>",
            "styles": ["narrative", "informational"],
        }))
        sys.exit(1)
    
    standard_id = sys.argv[1]
    grade = sys.argv[2]
    style = sys.argv[3]
    
    # Check if passage needed
    if "RL." not in standard_id and "RI." not in standard_id:
        print(json.dumps({
            "needed": False,
            "message": "Standard does not require passage"
        }))
        sys.exit(0)
    
    # Check cache
    cached = check_cache(standard_id)
    if cached:
        print(json.dumps({"source": "cache", "passage": cached}))
        sys.exit(0)
    
    config = GRADE_CONFIG.get(grade, GRADE_CONFIG["3"])
    
    print(json.dumps({
        "action": "generate_passage",
        "standard_id": standard_id,
        "grade": grade,
        "style": style,
        "requirements": {
            "word_count": config["words"],
            "age_group": config["age"],
            "readability": f"Flesch-Kincaid Grade {config['fk']}",
        },
        "instructions": f"""
Generate a {style} passage for grade {grade} students (ages {config['age']}).

Requirements:
- Word count: {config['words']}
- Readability: Flesch-Kincaid Grade Level {config['fk']}
- Style: {'Story, fable, or folktale' if style == 'narrative' else 'Article or explanatory text'}
- Content: Allow comprehension questions about the passage

Return ONLY the passage text, no explanations.
""",
        "cache_path": str(get_cache_path(standard_id)),
    }, indent=2))


if __name__ == "__main__":
    main()
