#!/usr/bin/env python3
"""
Populate missing curriculum fields using DIRECT Anthropic API calls.

This is more reliable than the SDK-based approach for batch operations.
It reads the populate-curriculum skill instructions and sends them directly
to the Anthropic API.

Usage:
  cd agent_sdk_v2
  python scripts/populate_curriculum_direct.py --dry-run
  python scripts/populate_curriculum_direct.py --limit 10
  python scripts/populate_curriculum_direct.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parents[1]

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

CURRICULUM_MD = (
    ROOT
    / ".claude"
    / "skills"
    / "ela-question-generation"
    / "reference"
    / "curriculum.md"
)

POPULATE_SKILL_MD = ROOT / ".claude" / "skills" / "populate-curriculum" / "SKILL.md"

BENCHMARK_GLOB = "grade-*-ela-benchmark.jsonl"


@dataclass(frozen=True)
class CurriculumNeed:
    standard_id: str
    standard_description: str
    grade: str
    needs_objectives: bool
    needs_boundaries: bool
    needs_misconceptions: bool


_STD_ID_RE = re.compile(r"^Standard ID:\s*(.+?)\s*$", re.MULTILINE)
_STD_DESC_RE = re.compile(r"^Standard Description:\s*(.+?)\s*$", re.MULTILINE)


def _infer_grade_from_standard_id(standard_id: str) -> str | None:
    parts = standard_id.split(".")
    if len(parts) >= 4 and parts[3].isdigit():
        return parts[3]
    return None


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                raise RuntimeError(f"Invalid JSONL in {path} at line {line_no}: {e}") from e
    return out


def build_benchmark_metadata(data_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    id_to_desc: dict[str, str] = {}
    id_to_grade: dict[str, str] = {}
    files = sorted(data_dir.glob(BENCHMARK_GLOB))
    for fp in files:
        for obj in _read_jsonl(fp):
            skills = obj.get("skills") or {}
            sid = (skills.get("substandard_id") or "").strip()
            if not sid or not sid.startswith("CCSS.ELA-LITERACY."):
                continue
            if sid not in id_to_desc:
                id_to_desc[sid] = (skills.get("substandard_description") or "").strip()
            if sid not in id_to_grade:
                id_to_grade[sid] = str(obj.get("grade") or "").strip()
    return id_to_desc, id_to_grade


def split_blocks(curriculum_text: str) -> list[str]:
    blocks = [b.strip() for b in curriculum_text.split("\n---\n") if b.strip()]
    return blocks


def _section_body(block: str, header: str, next_header: str) -> str:
    pat = re.compile(
        rf"{re.escape(header)}:\s*\n([\s\S]*?)\n\n{re.escape(next_header)}:",
        re.MULTILINE,
    )
    m = pat.search(block)
    return (m.group(1).strip() if m else "")


def analyze_block_need(block: str) -> CurriculumNeed | None:
    m_id = _STD_ID_RE.search(block)
    if not m_id:
        return None
    sid = m_id.group(1).strip()
    if not sid.startswith("CCSS.ELA-LITERACY."):
        return None

    m_desc = _STD_DESC_RE.search(block)
    desc = (m_desc.group(1).strip() if m_desc else "")

    objectives = _section_body(block, "Learning Objectives", "Assessment Boundaries")
    boundaries = _section_body(block, "Assessment Boundaries", "Common Misconceptions")
    misconceptions = _section_body(block, "Common Misconceptions", "Difficulty Definitions")

    needs_obj = (not objectives) or ("*None specified*" in objectives)
    needs_bnd = (not boundaries) or ("*None specified*" in boundaries)
    needs_mis = (not misconceptions) or ("*None specified*" in misconceptions)

    grade = _infer_grade_from_standard_id(sid) or ""

    return CurriculumNeed(
        standard_id=sid,
        standard_description=desc,
        grade=grade,
        needs_objectives=needs_obj,
        needs_boundaries=needs_bnd,
        needs_misconceptions=needs_mis,
    )


def _format_bullets(items: list | str | None) -> str:
    if not items:
        return "*None specified*"
    if isinstance(items, list):
        cleaned = [str(x).strip() for x in items if str(x).strip()]
        return "\n".join([f"* {x}" for x in cleaned]) if cleaned else "*None specified*"
    s = str(items).strip()
    return s if s else "*None specified*"


def _update_curriculum_md_section(text: str, standard_id: str, data: dict) -> tuple[str, bool]:
    """Update curriculum.md in-place for a given Standard ID."""
    if f"Standard ID: {standard_id}" not in text:
        return text, False

    block_re = re.compile(
        rf"(Standard ID:\s*{re.escape(standard_id)}[\s\S]*?)(?=\n---\n|\Z)",
        re.MULTILINE,
    )
    m = block_re.search(text)
    if not m:
        return text, False

    block = m.group(1)

    objectives = _format_bullets(data.get("learning_objectives"))
    boundaries = _format_bullets(data.get("assessment_boundaries"))
    misconceptions = _format_bullets(data.get("common_misconceptions"))

    def replace_section(block_text: str, header: str, next_header: str, new_body: str) -> str:
        pattern = re.compile(
            rf"({re.escape(header)}:\s*\n)([\s\S]*?)(\n\n{re.escape(next_header)}:)",
            re.MULTILINE,
        )
        if pattern.search(block_text):
            return pattern.sub(rf"\1{new_body}\3", block_text)
        return block_text

    block2 = block
    block2 = replace_section(block2, "Learning Objectives", "Assessment Boundaries", objectives)
    block2 = replace_section(block2, "Assessment Boundaries", "Common Misconceptions", boundaries)

    mis_re = re.compile(
        r"(Common Misconceptions:\s*\n)([\s\S]*?)(\n\nDifficulty Definitions:)",
        re.MULTILINE,
    )
    if mis_re.search(block2):
        block2 = mis_re.sub(rf"\1{misconceptions}\3", block2)

    new_text = text[: m.start(1)] + block2 + text[m.end(1) :]
    return new_text, True


def extract_json(text: str) -> str:
    """Extract first JSON object from text."""
    text = text.strip()
    if not text:
        return ""
    
    # Try code fence first
    fence_match = re.search(r"```(?:json)?\s*(\{)", text, re.MULTILINE)
    if fence_match:
        start_pos = fence_match.end(1) - 1
        depth = 0
        for i in range(start_pos, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start_pos:i+1].strip()
    
    # Fallback: find first {...}
    start = text.find("{")
    if start < 0:
        return text
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text


def call_anthropic_api(
    standard_id: str,
    standard_description: str,
    grade: str,
    skill_instructions: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """
    Call Anthropic API directly to generate curriculum data.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are a curriculum specialist. Follow these instructions to generate curriculum data:

{skill_instructions}

---

Generate curriculum data for:

Standard ID: {standard_id}
Standard Description: {standard_description}
Grade: {grade}

Return ONLY a JSON object with these fields:
- standard_id
- learning_objectives (array of 2-4 strings)
- assessment_boundaries (array of 1-3 strings)
- common_misconceptions (array of 3-5 strings)

No markdown code fences. Just the raw JSON object.
"""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        
        json_str = extract_json(text)
        if not json_str:
            return {"success": False, "error": "No JSON in response", "raw": text[:500]}
        
        data = json.loads(json_str)
        return {"success": True, "data": data}
    
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON parse error: {e}", "raw": text[:500] if text else ""}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Populate missing curriculum fields (direct API)")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be populated")
    ap.add_argument("--limit", type=int, default=None, help="Only process first N standards")
    ap.add_argument(
        "--only-benchmark",
        action="store_true",
        default=True,
        help="Only populate standards referenced by benchmark files",
    )
    ap.add_argument("--all", action="store_true", help="Populate ALL standards in curriculum.md")
    ap.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds)")
    ap.add_argument(
        "--model",
        default=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        help="Model to use",
    )
    args = ap.parse_args()
    if args.all:
        args.only_benchmark = False

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    if not CURRICULUM_MD.exists():
        print(f"ERROR: curriculum.md not found at {CURRICULUM_MD}", file=sys.stderr)
        return 2

    # Load skill instructions for context
    skill_instructions = ""
    if POPULATE_SKILL_MD.exists():
        skill_instructions = POPULATE_SKILL_MD.read_text(encoding="utf-8")
        # Strip YAML frontmatter
        if skill_instructions.startswith("---"):
            parts = skill_instructions.split("---", 2)
            if len(parts) >= 3:
                skill_instructions = parts[2].strip()

    curriculum_text = CURRICULUM_MD.read_text(encoding="utf-8")
    blocks = split_blocks(curriculum_text)

    id_to_desc, id_to_grade = build_benchmark_metadata(ROOT / "data")

    needs: list[CurriculumNeed] = []
    for block in blocks:
        need = analyze_block_need(block)
        if not need:
            continue
        if need.needs_objectives or need.needs_boundaries or need.needs_misconceptions:
            grade = (id_to_grade.get(need.standard_id) or need.grade or "").strip() or "3"
            desc = (id_to_desc.get(need.standard_id) or need.standard_description or "").strip()
            needs.append(
                CurriculumNeed(
                    standard_id=need.standard_id,
                    standard_description=desc,
                    grade=grade,
                    needs_objectives=need.needs_objectives,
                    needs_boundaries=need.needs_boundaries,
                    needs_misconceptions=need.needs_misconceptions,
                )
            )

    if args.only_benchmark:
        benchmark_ids = set(id_to_desc.keys()) | set(id_to_grade.keys())
        needs = [n for n in needs if n.standard_id in benchmark_ids]

    needs.sort(key=lambda n: n.standard_id)

    total = len(needs)
    if args.limit is not None:
        needs = needs[: args.limit]

    print(f"Curriculum blocks:                     {len(blocks)}")
    print(f"Standards needing population (total):  {total}")
    print(f"Standards selected this run:           {len(needs)}")
    print(f"Model:                                 {args.model}")
    print(f"Delay between calls:                   {args.delay}s")

    if not needs:
        print("Nothing to populate.")
        return 0

    if args.dry_run:
        print("\nDry run (first 30):")
        for n in needs[:30]:
            flags = []
            if n.needs_objectives:
                flags.append("objectives")
            if n.needs_boundaries:
                flags.append("boundaries")
            if n.needs_misconceptions:
                flags.append("misconceptions")
            print(f"  - {n.standard_id} (grade {n.grade}): {', '.join(flags)}")
        return 0

    n_ok = 0
    n_skip = 0
    n_fail = 0

    # Re-read curriculum for updates (in case it changed)
    curriculum_text = CURRICULUM_MD.read_text(encoding="utf-8")

    for i, n in enumerate(needs, start=1):
        sid = n.standard_id
        desc = (n.standard_description or "").strip()
        grade = (n.grade or "").strip() or "3"

        print(f"\n[{i}/{len(needs)}] {sid} (grade {grade})")

        # Re-check if this standard still needs population (in case file was updated)
        # Find the block for this standard and verify it still has *None specified*
        block_match = re.search(
            rf"(Standard ID:\s*{re.escape(sid)}[\s\S]*?)(?=\n---\n|\Z)",
            curriculum_text,
            re.MULTILINE,
        )
        if block_match:
            block_text = block_match.group(1)
            obj_body = _section_body(block_text, "Learning Objectives", "Assessment Boundaries")
            bnd_body = _section_body(block_text, "Assessment Boundaries", "Common Misconceptions")
            mis_body = _section_body(block_text, "Common Misconceptions", "Difficulty Definitions")
            
            still_needs = (
                (not obj_body or "*None specified*" in obj_body) or
                (not bnd_body or "*None specified*" in bnd_body) or
                (not mis_body or "*None specified*" in mis_body)
            )
            
            if not still_needs:
                print("  SKIP: already populated")
                n_skip += 1
                continue

        if not desc:
            print("  SKIP: missing standard_description")
            n_skip += 1
            continue

        result = call_anthropic_api(
            standard_id=sid,
            standard_description=desc,
            grade=grade,
            skill_instructions=skill_instructions,
            api_key=api_key,
            model=args.model,
        )

        if not result.get("success"):
            print(f"  FAIL: {result.get('error', 'Unknown error')}")
            if result.get("raw"):
                print(f"  Raw: {result['raw'][:200]}")
            n_fail += 1
            time.sleep(args.delay)
            continue

        data = result["data"]
        updated_text, updated = _update_curriculum_md_section(curriculum_text, sid, data)

        if not updated:
            print(f"  FAIL: Could not update curriculum.md (standard not found in file)")
            n_fail += 1
        else:
            curriculum_text = updated_text
            CURRICULUM_MD.write_text(curriculum_text, encoding="utf-8")
            print("  OK: populated and saved")
            n_ok += 1

        time.sleep(args.delay)

    print("\n" + "=" * 50)
    print("Done.")
    print(f"Populated: {n_ok}")
    print(f"Skipped:   {n_skip}")
    print(f"Failed:    {n_fail}")
    print(f"Updated:   {CURRICULUM_MD}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
