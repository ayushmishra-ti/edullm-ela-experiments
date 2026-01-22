#!/usr/bin/env python3
"""
Upload the ela-mcq-generation skill to Anthropic and print the skill_id.

Set CCAPI_ELA_MCQ_SKILL_ID in .env to use Skills API mode in generate_one.

Usage:
  From project root (ccapi):
    python scripts/upload_skill.py

  Env: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# try:
#     from dotenv import load_dotenv
#     load_dotenv(ROOT / ".env", override=False)
# except ImportError:
#     pass

_api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def main() -> int:
    if not _api_key:
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1
    try:
        import anthropic
    except ImportError:
        print("anthropic not installed. pip install anthropic", file=sys.stderr)
        return 1

    skill_dir = ROOT / "skills" / "ela-mcq-generation"
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        print(f"SKILL.md not found in {skill_dir}", file=sys.stderr)
        return 1

    print(f"Uploading skill from: {skill_file}")

    # Build files: (filename, file-like). Prefer anthropic.lib.files_from_dir if available.
    import io
    try:
        from anthropic.lib import files_from_dir as ffd
        files_arg = ffd(str(skill_dir))
    except ImportError:
        files_arg = [("SKILL.md", io.BytesIO(skill_file.read_bytes()))]

    client = anthropic.Anthropic(api_key=_api_key)

    try:
        skill = client.beta.skills.create(
            display_title="Grade 3 ELA MCQ Generation",
            files=files_arg,
            betas=["skills-2025-10-02"],
        )
    except Exception as e:
        print(f"Create failed: {e}", file=sys.stderr)
        return 1

    print(f"Skill ID: {skill.id}")
    print(f"Latest version: {getattr(skill, 'latest_version', 'N/A')}")
    print("")
    print("Add to .env:")
    print(f"  CCAPI_ELA_MCQ_SKILL_ID={skill.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
