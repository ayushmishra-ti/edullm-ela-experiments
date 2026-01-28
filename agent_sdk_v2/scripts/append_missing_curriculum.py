#!/usr/bin/env python3
"""
Append missing ELA standards into agent_sdk_v2 curriculum.md.

This script:
- reads all benchmark JSONL requests in agent_sdk_v2/data/grade-*-ela-benchmark.jsonl
- collects unique skills.substandard_id values
- compares against Standard IDs already present in:
    agent_sdk_v2/.claude/skills/ela-question-generation/reference/curriculum.md
- for missing IDs, extracts the matching block from:
    original_curriculm-data/ccss_curriculum.md
- appends found blocks to curriculum.md

Usage:
  cd agent_sdk_v2
  python scripts/append_missing_curriculum.py --dry-run
  python scripts/append_missing_curriculum.py
  python scripts/append_missing_curriculum.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BENCHMARK_GLOB = "grade-*-ela-benchmark.jsonl"
DEFAULT_CURRICULUM_PATH = (
    ROOT
    / ".claude"
    / "skills"
    / "ela-question-generation"
    / "reference"
    / "curriculum.md"
)
DEFAULT_SOURCE_PATH = ROOT.parents[0] / "original_curriculm-data" / "ccss_curriculum.md"


STANDARD_ID_RE = re.compile(r"^Standard ID:\s*(.+?)\s*$")


def iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception as e:
                raise RuntimeError(f"Invalid JSONL in {path} at line {line_no}: {e}") from e


def collect_benchmark_standard_ids(data_dir: Path, pattern: str) -> set[str]:
    ids: set[str] = set()
    files = sorted(data_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No benchmark files found at {data_dir} matching {pattern}")

    for fp in files:
        for obj in iter_jsonl(fp):
            skills = obj.get("skills") or {}
            sid = skills.get("substandard_id")
            if isinstance(sid, str) and sid.strip():
                ids.add(sid.strip())
    return ids


def collect_curriculum_standard_ids(curriculum_md: Path) -> set[str]:
    ids: set[str] = set()
    with open(curriculum_md, "r", encoding="utf-8") as f:
        for line in f:
            m = STANDARD_ID_RE.match(line.strip("\n"))
            if m:
                ids.add(m.group(1).strip())
    return ids


def extract_blocks_from_source(
    source_md: Path, *, wanted_ids: set[str]
) -> tuple[dict[str, str], set[str]]:
    """
    Scan the giant curriculum file once and extract blocks for wanted_ids.

    Returns (found_blocks_by_id, remaining_ids_not_found_in_source).
    """
    remaining = set(wanted_ids)
    found: dict[str, str] = {}

    # Block delimiter in these curriculum files is a line containing just '---'
    delimiter = "---"
    block_lines: list[str] = []

    def flush_block():
        nonlocal block_lines, remaining, found
        if not block_lines:
            return
        # Identify Standard ID in the block
        sid = None
        for ln in block_lines:
            m = STANDARD_ID_RE.match(ln)
            if m:
                sid = m.group(1).strip()
                break
        if sid and sid in remaining:
            text = "\n".join(block_lines).rstrip()  # normalize trailing whitespace
            found[sid] = text
            remaining.remove(sid)

        block_lines = []

    with open(source_md, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.strip() == delimiter:
                flush_block()
                if not remaining:
                    break
                continue
            block_lines.append(line)

        # Flush trailing block if file doesn't end with delimiter
        flush_block()

    return found, remaining


def append_blocks(curriculum_md: Path, blocks: list[str]) -> None:
    """
    Append blocks to curriculum.md separated by the canonical delimiter.
    """
    if not blocks:
        return

    existing = curriculum_md.read_text(encoding="utf-8")
    out = existing.rstrip() + "\n\n"
    for i, block in enumerate(blocks):
        out += block.rstrip() + "\n\n---\n\n"
    curriculum_md.write_text(out, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Append missing standards to curriculum.md")
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data",
        help="Directory containing benchmark JSONL files",
    )
    ap.add_argument(
        "--benchmark-glob",
        default=DEFAULT_BENCHMARK_GLOB,
        help=f"Glob for benchmark JSONL files (default: {DEFAULT_BENCHMARK_GLOB})",
    )
    ap.add_argument(
        "--curriculum",
        type=Path,
        default=DEFAULT_CURRICULUM_PATH,
        help="Target curriculum.md to append to",
    )
    ap.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_PATH,
        help="Source ccss_curriculum.md to extract blocks from",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N missing standards (for testing)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be appended without writing",
    )
    args = ap.parse_args()

    if not args.curriculum.exists():
        print(f"ERROR: curriculum.md not found at {args.curriculum}", file=sys.stderr)
        return 2
    if not args.source.exists():
        print(f"ERROR: source curriculum not found at {args.source}", file=sys.stderr)
        return 2

    needed_ids = collect_benchmark_standard_ids(args.data_dir, args.benchmark_glob)
    # Keep this script tightly scoped to ELA benchmark IDs
    needed_ids = {sid for sid in needed_ids if sid.startswith("CCSS.ELA-LITERACY.")}

    existing_ids = collect_curriculum_standard_ids(args.curriculum)

    missing_ids = sorted(needed_ids - existing_ids)
    if args.limit is not None:
        missing_ids = missing_ids[: args.limit]
    print(f"Benchmark unique ELA Standard IDs: {len(needed_ids)}")
    print(f"Curriculum existing Standard IDs:  {len(existing_ids)}")
    print(f"Missing Standard IDs (selected):  {len(missing_ids)}")

    if not missing_ids:
        print("Nothing to do.")
        return 0

    wanted = set(missing_ids)
    found, remaining = extract_blocks_from_source(args.source, wanted_ids=wanted)

    print(f"Found in source:                  {len(found)}")
    print(f"Not found in source:              {len(remaining)}")
    if remaining:
        # show a few to help debugging
        preview = sorted(list(remaining))[:10]
        print("  Examples not found:")
        for sid in preview:
            print(f"  - {sid}")

    # Preserve deterministic append order
    blocks_to_append = [found[sid] for sid in missing_ids if sid in found]

    if args.dry_run:
        print("\nDry run: would append these Standard IDs (first 30 shown):")
        for sid in [sid for sid in missing_ids if sid in found][:30]:
            print(f"  - {sid}")
        return 0

    append_blocks(args.curriculum, blocks_to_append)
    print(f"\nAppended {len(blocks_to_append)} blocks to: {args.curriculum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

