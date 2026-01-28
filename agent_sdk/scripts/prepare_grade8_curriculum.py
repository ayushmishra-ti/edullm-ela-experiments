#!/usr/bin/env python3
"""
Prepare grade-8 ELA curriculum for Cloud Run:

1) Read unique substandard_ids from a benchmark JSONL file.
2) Extract matching Standard blocks from the combined CCSS curriculum markdown.
3) Append those blocks into the skill's deployed curriculum.md (default; no data loss).
4) Populate missing Learning Objectives / Assessment Boundaries / Common Misconceptions
   by calling the existing populate_curriculum.py script once per standard (only when missing).

This produces a curriculum.md that is ready to bake into the Docker image and redeploy.

Usage:
  python scripts/prepare_grade8_curriculum.py
  python scripts/prepare_grade8_curriculum.py --limit 10
  python scripts/prepare_grade8_curriculum.py --benchmark data/grade-8-ela-benchmark.jsonl
  python scripts/prepare_grade8_curriculum.py --source .claude/skills/ela-question-generation/references/ccss_curriculum.md
  python scripts/prepare_grade8_curriculum.py --output .claude/skills/ela-question-generation/references/curriculum.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".claude" / "skills" / "ela-question-generation"
DEFAULT_BENCHMARK = ROOT / "data" / "grade-8-ela-benchmark.jsonl"
DEFAULT_SOURCE = SKILL_DIR / "references" / "ccss_curriculum.md"
DEFAULT_OUTPUT = SKILL_DIR / "references" / "curriculum.md"
LOOKUP_SCRIPT = SKILL_DIR / "scripts" / "lookup_curriculum.py"
POPULATE_SCRIPT = SKILL_DIR / "scripts" / "populate_curriculum.py"


@dataclass(frozen=True)
class StandardReq:
    standard_id: str
    standard_description: str


def load_benchmark_requests(path: Path) -> list[StandardReq]:
    """Load benchmark JSONL and return unique (id, description) pairs preserving first-seen order."""
    seen: set[str] = set()
    out: list[StandardReq] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            skills = obj.get("skills") or {}
            sid = (skills.get("substandard_id") or "").strip()
            sdesc = (skills.get("substandard_description") or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            out.append(StandardReq(standard_id=sid, standard_description=sdesc))
    return out


def extract_blocks_by_standard_id(source_path: Path, needed_ids: set[str]) -> dict[str, str]:
    """
    Stream-parse source curriculum markdown and extract full blocks separated by '---'.
    Returns mapping: standard_id -> block text (without trailing separator).
    """
    found: dict[str, str] = {}
    block_lines: list[str] = []

    def flush_block() -> None:
        nonlocal block_lines, found
        if not block_lines:
            return
        text = "".join(block_lines)
        # Cheap parse: find Standard ID line
        for line in block_lines:
            if line.startswith("Standard ID:"):
                sid = line.split("Standard ID:", 1)[1].strip()
                if sid in needed_ids and sid not in found:
                    found[sid] = text.rstrip()
                break
        block_lines = []

    with open(source_path, "r", encoding="utf-8") as f:
        for line in f:
            # A block separator line in this corpus is exactly '---' (possibly with newline).
            if line.strip() == "---":
                flush_block()
                continue
            block_lines.append(line)

    flush_block()
    return found


def write_curriculum_md(output_path: Path, ordered_ids: list[str], blocks: dict[str, str]) -> None:
    raise RuntimeError("write_curriculum_md() should not be called directly; use write_or_append_curriculum_md().")


def _existing_standard_ids(path: Path) -> set[str]:
    """
    Parse an existing curriculum markdown file and return all Standard IDs found.
    Blocks are separated by '---'.
    """
    if not path.exists():
        return set()
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return set()

    ids: set[str] = set()
    for entry in content.split("---"):
        for line in entry.splitlines():
            if line.startswith("Standard ID:"):
                ids.add(line.split("Standard ID:", 1)[1].strip())
                break
    return ids


def write_or_append_curriculum_md(
    output_path: Path,
    ordered_ids: list[str],
    blocks: dict[str, str],
    *,
    overwrite: bool,
) -> tuple[int, int]:
    """
    Writes curriculum.md.

    - If overwrite=True: replaces file with the selected blocks.
    - If overwrite=False (default): appends missing blocks only.

    Returns: (n_written_or_appended, n_skipped_existing)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing_ids = _existing_standard_ids(output_path) if not overwrite else set()
    n_skipped = 0
    selected_blocks: list[str] = []

    for sid in ordered_ids:
        block = blocks.get(sid)
        if not block:
            continue
        if sid in existing_ids:
            n_skipped += 1
            continue
        selected_blocks.append(block.strip() + "\n")

    if overwrite:
        output_path.write_text("\n---\n\n".join(selected_blocks).strip() + "\n", encoding="utf-8")
        return (len(selected_blocks), n_skipped)

    if not output_path.exists() or output_path.read_text(encoding="utf-8").strip() == "":
        output_path.write_text("\n---\n\n".join(selected_blocks).strip() + "\n", encoding="utf-8")
        return (len(selected_blocks), n_skipped)

    if not selected_blocks:
        return (0, n_skipped)

    existing = output_path.read_text(encoding="utf-8")
    tail = existing.rstrip()
    if not tail.endswith("---"):
        tail = tail + "\n\n---\n\n"
    else:
        tail = tail + "\n\n"

    output_path.write_text(tail + "\n---\n\n".join(selected_blocks).strip() + "\n", encoding="utf-8")
    return (len(selected_blocks), n_skipped)


def run_lookup(standard_id: str) -> dict:
    cmd = [sys.executable, str(LOOKUP_SCRIPT), standard_id]
    out = subprocess.check_output(cmd, cwd=str(ROOT), stderr=subprocess.STDOUT)
    return json.loads(out.decode("utf-8", errors="replace"))


def run_populate(standard_id: str, standard_description: str) -> dict:
    cmd = [sys.executable, str(POPULATE_SCRIPT), standard_id, standard_description]
    out = subprocess.check_output(cmd, cwd=str(ROOT), stderr=subprocess.STDOUT)
    return json.loads(out.decode("utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare grade-8 curriculum.md and populate missing fields")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N unique standards (for quick testing)",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Populate missing learning objectives/boundaries/misconceptions via Claude",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output curriculum.md instead of appending (DANGEROUS).",
    )
    args = parser.parse_args()

    if not args.benchmark.exists():
        print(f"Error: benchmark not found: {args.benchmark}", file=sys.stderr)
        return 2
    if not args.source.exists():
        print(f"Error: source curriculum not found: {args.source}", file=sys.stderr)
        return 2
    if not LOOKUP_SCRIPT.exists():
        print(f"Error: lookup script not found: {LOOKUP_SCRIPT}", file=sys.stderr)
        return 2
    if not POPULATE_SCRIPT.exists():
        print(f"Error: populate script not found: {POPULATE_SCRIPT}", file=sys.stderr)
        return 2

    reqs = load_benchmark_requests(args.benchmark)
    if args.limit:
        reqs = reqs[: args.limit]
    needed_ids = {r.standard_id for r in reqs}

    print(f"Benchmark: {args.benchmark}")
    print(f"Source:    {args.source}")
    print(f"Output:    {args.output}")
    print(f"Standards: {len(reqs)} unique")

    blocks = extract_blocks_by_standard_id(args.source, needed_ids)
    missing_blocks = [r.standard_id for r in reqs if r.standard_id not in blocks]
    if missing_blocks:
        print(f"Warning: {len(missing_blocks)} standards not found in source curriculum.")
        for sid in missing_blocks[:10]:
            print(f"  - {sid}")

    ordered_ids = [r.standard_id for r in reqs]
    n_written, n_skipped = write_or_append_curriculum_md(
        args.output,
        ordered_ids,
        blocks,
        overwrite=args.overwrite,
    )
    if args.overwrite:
        print(f"Overwrote curriculum.md with {n_written} blocks: {args.output}")
    else:
        print(f"Appended {n_written} new blocks (skipped {n_skipped} existing): {args.output}")

    if not args.populate:
        print("Populate step skipped (pass --populate to fill missing fields).")
        return 0

    # Populate missing fields only
    n_populated = 0
    n_skipped = 0
    n_failed = 0

    for i, r in enumerate(reqs, start=1):
        sid = r.standard_id
        desc = r.standard_description or ""
        print(f"[{i}/{len(reqs)}] {sid} ...", end=" ", flush=True)
        try:
            lookup = run_lookup(sid)
            if not lookup.get("found"):
                print("SKIP (not found in output)")
                n_skipped += 1
                continue

            needs = (not lookup.get("has_objectives")) or (not lookup.get("has_boundaries")) or (not lookup.get("has_misconceptions"))
            if not needs:
                print("SKIP (already populated)")
                n_skipped += 1
                continue

            if not desc:
                # populate script needs a description; fall back to curriculum description if present
                desc = (lookup.get("standard_description") or "").strip()

            if not desc:
                print("FAIL (missing description)")
                n_failed += 1
                continue

            _ = run_populate(sid, desc)
            print("OK (populated)")
            n_populated += 1
        except subprocess.CalledProcessError as e:
            msg = e.output.decode("utf-8", errors="replace") if getattr(e, "output", None) else str(e)
            print("FAIL")
            print(msg)
            n_failed += 1
        except Exception as e:
            print("FAIL")
            print(str(e))
            n_failed += 1

    print("\nDone.")
    print(f"Populated: {n_populated}")
    print(f"Skipped:   {n_skipped}")
    print(f"Failed:    {n_failed}")
    print(f"Output curriculum.md: {args.output}")

    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

