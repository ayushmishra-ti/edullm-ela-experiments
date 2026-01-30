#!/usr/bin/env python3
"""Debug format issues in generated results."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    # Check the latest generated results
    results_file = ROOT / "outputs" / "random_sample_results.json"
    
    if not results_file.exists():
        print(f"File not found: {results_file}")
        return
    
    d = json.load(open(results_file))
    items = d.get('generated_content', [])
    errors = d.get('errors', [])
    
    print(f"Generated items: {len(items)}")
    print(f"Errors: {len(errors)}")
    
    if items:
        print("\n--- Checking all items for format issues ---")
        issues_found = []
        
        for item in items:
            item_id = item.get('id', 'unknown')
            content = item.get('content', {})
            request = item.get('request', {})
            qtype = request.get('type', 'unknown')
            
            problems = []
            
            # Check answer_options
            opts = content.get('answer_options')
            if qtype in ['mcq', 'msq']:
                if opts is None:
                    problems.append("Missing answer_options")
                elif not isinstance(opts, list):
                    problems.append(f"answer_options not list: {type(opts).__name__}")
                elif len(opts) != 4:
                    problems.append(f"Wrong option count: {len(opts)}")
                elif opts and isinstance(opts[0], dict):
                    keys = set(opts[0].keys())
                    if keys != {'key', 'text'}:
                        problems.append(f"Wrong option format: {keys}")
            
            # Check answer format
            answer = content.get('answer')
            if qtype == 'msq' and not isinstance(answer, list):
                problems.append(f"MSQ answer not list: {type(answer).__name__}")
            if qtype == 'mcq' and isinstance(answer, list):
                problems.append("MCQ answer is list")
            
            # Check required fields
            if 'question' not in content:
                problems.append("Missing question")
            if 'answer' not in content:
                problems.append("Missing answer")
            
            if problems:
                issues_found.append((item_id, qtype, problems))
        
        if issues_found:
            print(f"\nFound {len(issues_found)} items with issues:")
            for item_id, qtype, probs in issues_found:
                print(f"  {item_id} ({qtype}):")
                for p in probs:
                    print(f"    - {p}")
        else:
            print("\nNo format issues found in generated items!")
        
        # Show sample item
        print("\n--- Sample item (first) ---")
        if items:
            item = items[0]
            print(json.dumps({
                "id": item.get("id"),
                "content_keys": list(item.get("content", {}).keys()),
                "answer": item.get("content", {}).get("answer"),
                "options_count": len(item.get("content", {}).get("answer_options", [])),
            }, indent=2))


if __name__ == "__main__":
    main()
