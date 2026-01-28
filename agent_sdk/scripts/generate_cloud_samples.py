#!/usr/bin/env python3
"""
Generate samples from the deployed Cloud Run /generate endpoint and save them in
an InceptBench-compatible batch file ({"generated_content": [...]}).

Usage:
  python scripts/generate_cloud_samples.py
  python scripts/generate_cloud_samples.py -n 15
  python scripts/generate_cloud_samples.py -n 15 -r
  python scripts/generate_cloud_samples.py -i data/sample_requests.jsonl -o outputs/cloud_endpoint_samples.json
  python scripts/generate_cloud_samples.py --endpoint https://.../generate
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ENDPOINT = "https://inceptagentic-skill-mcq-413562643011.us-central1.run.app/generate"


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_requests_jsonl(path: Path) -> list[dict]:
    requests: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            requests.append(json.loads(line))
    return requests


def post_json(url: str, payload: dict, timeout_s: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url=url,
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def extract_generated_items(resp: dict) -> list[dict]:
    """
    Cloud Run returns:
      { ..., "generatedContent": { "generated_content": [ ... ] } }
    Be tolerant to minor variations.
    """
    wrapper = resp.get("generatedContent") or resp.get("generated_content") or {}
    if isinstance(wrapper, list):
        return [i for i in wrapper if isinstance(i, dict)]
    if isinstance(wrapper, dict):
        items = wrapper.get("generated_content") or wrapper.get("generatedContent") or []
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate samples from Cloud Run endpoint and save as a batch JSON."
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=DEFAULT_ENDPOINT,
        help=f"Cloud Run /generate endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=ROOT / "data" / "sample_requests.jsonl",
        help="Input requests JSONL (one request per line)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=ROOT / "outputs" / "cloud_endpoint_samples.json",
        help="Output JSON file (InceptBench-compatible wrapper)",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=15,
        help="How many requests to send (default: 15)",
    )
    parser.add_argument(
        "--random",
        "-r",
        action="store_true",
        help="Randomly sample requests (shuffle before taking first N)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed (only used with --random)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Per-request timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Sleep seconds between requests (default: 0)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: input not found: {args.input}", file=sys.stderr)
        return 2

    requests_list = load_requests_jsonl(args.input)
    if not requests_list:
        print(f"Error: no requests found in: {args.input}", file=sys.stderr)
        return 2

    if args.random:
        rng = random.Random(args.seed)
        rng.shuffle(requests_list)

    limit = min(args.limit, len(requests_list))
    requests_list = requests_list[:limit]

    print(f"Endpoint: {args.endpoint}")
    print(f"Loading requests from: {args.input}")
    print(f"Sending {len(requests_list)} requests")
    print(f"Saving to: {args.output}")
    print()

    generated: list[dict] = []
    errors: list[dict] = []

    for idx, req_payload in enumerate(requests_list, start=1):
        skill_id = (req_payload.get("skills") or {}).get("substandard_id") or "unknown"
        qtype = req_payload.get("type", "mcq")
        difficulty = req_payload.get("difficulty", "medium")
        label = f"{skill_id} {qtype} {difficulty}"

        print(f"[{idx}/{len(requests_list)}] {label}...", end=" ", flush=True)
        try:
            resp = post_json(args.endpoint, req_payload, timeout_s=args.timeout)
            items = extract_generated_items(resp)
            if not items:
                errors.append(
                    {
                        "request": req_payload,
                        "error": "no_generated_content_in_response",
                        "response_keys": sorted(list(resp.keys())) if isinstance(resp, dict) else None,
                    }
                )
                print("FAIL (no generated content)")
            else:
                generated.extend(items)
                print(f"OK (+{len(items)})")
        except HTTPError as e:
            body = None
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = None
            errors.append(
                {
                    "request": req_payload,
                    "error": "http_error",
                    "status": getattr(e, "code", None),
                    "body": body,
                }
            )
            print(f"FAIL (HTTP {getattr(e, 'code', '??')})")
        except URLError as e:
            errors.append({"request": req_payload, "error": "url_error", "reason": str(e.reason)})
            print("FAIL (URL error)")
        except Exception as e:
            errors.append({"request": req_payload, "error": "exception", "message": str(e)})
            print("FAIL (exception)")

        if args.sleep and idx < len(requests_list):
            time.sleep(args.sleep)

    out = {
        "generated_content": generated,
        "errors": errors,
        "metadata": {
            "endpoint": args.endpoint,
            "input": str(args.input),
            "requested": limit,
            "generated_items": len(generated),
            "errors": len(errors),
            "timestamp": _utc_ts(),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print()
    print("Done.")
    print(f"Generated items: {len(generated)}")
    print(f"Errors: {len(errors)}")
    print(f"Wrote: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

