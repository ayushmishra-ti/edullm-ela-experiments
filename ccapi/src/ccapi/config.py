"""Configuration from environment and .env."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    _load = load_dotenv
except ImportError:
    def _load(*_args, **_kwargs): pass

# Load .env from project root (ccapi folder)
_ROOT = Path(__file__).resolve().parents[2]
if (_ROOT / ".env").exists():
    _load(_ROOT / ".env", override=False)

def _str(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()

def _path(key: str, default: Path | None = None) -> Path | None:
    v = _str(key)
    return Path(v) if v else default

ANTHROPIC_API_KEY = _str("ANTHROPIC_API_KEY")
CCAPI_ELA_MCQ_SKILL_ID = _str("CCAPI_ELA_MCQ_SKILL_ID")
CCAPI_POPULATE_CURRICULUM_SKILL_ID = _str("CCAPI_POPULATE_CURRICULUM_SKILL_ID")
INCEPT_API_KEY = _str("INCEPT_API_KEY")
CCAPI_BENCHMARK_PATH = _path("CCAPI_BENCHMARK_PATH")
CCAPI_LLM_MODEL = _str("CCAPI_LLM_MODEL") or "claude-sonnet-4-5-20250929"

# Skill file paths (for fallback when Skills API not used)
SKILL_PATH = _ROOT / "skills" / "ela-mcq-generation" / "SKILL.md"
POPULATE_CURRICULUM_SKILL_PATH = _ROOT / "skills" / "populate-curriculum" / "SKILL.md"
