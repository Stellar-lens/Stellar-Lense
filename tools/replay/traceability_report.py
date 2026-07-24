#!/usr/bin/env python3
import sys
import os
import json
import argparse
import time
import tempfile

EXIT_SUCCESS = 0
EXIT_INVALID_ARGS = 1
EXIT_CORRUPT_INPUT = 2
EXIT_TRACEABILITY_GAP = 3
EXIT_CHECKPOINT_ERROR = 4

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 5000

def parse_args():
    parser = argparse.ArgumentParser(description="LedgerLens Traceability Generator")
    parser.add_argument("--input", required=True, help="Path to input mapping JSON")
    parser.add_argument("--output", required=True, help="Path to output report file")
    parser.add_argument("--format", choices=["json", "human"], default="json", help="Output format")
    parser.add_argument("--dry-run", action="store_true", help="Perform validation without side effects")
    parser.add_argument("--resume-checkpoint", help="Path to checkpoint file for resuming execution")
    parser.add_argument("--strict", action="store_true", help="Fail if any invariant lacks test coverage")
    return parser.parse_args()

def validate_input_file(path):
    if not os.path.exists(path):
        sys.stderr.write(f"Error: File not found: {path}\n")
        sys.exit(EXIT_CORRUPT_INPUT)
    
    file_size = os.path.getsize(path)
    if file_size > MAX_INPUT_BYTES:
        sys.stderr.write(f"Error: Input file size {file_size} exceeds limit of {MAX_INPUT_BYTES} bytes\n")
        sys.exit(EXIT_CORRUPT_INPUT)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error parsing JSON input: {str(e)}\n")
        sys.exit(EXIT_CORRUPT_INPUT)

    if not isinstance(data, list):
        sys.stderr.write("Error: Root input JSON structure must be a list\n")
        sys.exit(EXIT_CORRUPT_INPUT)

    if len(data) > MAX_ITEMS:
        sys.stderr.write(f"Error: Exceeded maximum item limit of {MAX_ITEMS}\n")
        sys.exit(EXIT_CORRUPT_INPUT)

    return data

def process_traceability(items, checkpoint_data=None):
    processed_items = []
    total_invariants = 0
    covered_invariants = 0
    all_test_ids = set()

    start_index = 0
    if checkpoint_data and "last_index" in checkpoint_data:
        start_index = checkpoint_data["last_index"] + 1
        processed_items = checkpoint_data.get("processed_items", [])

    items_to_process = items[start_index:]
    sorted_items = sorted(items_to_process, key=lambda x: str(x.get("issue_id", "")))

    for raw_item in sorted_items:
        issue_id = str(raw_item.get("issue_id", "UNKNOWN"))
        title = str(raw_item.get("title", ""))
        invariants_raw = raw_item.get("invariants", [])

        if not isinstance(invariants_raw, list):
            sys.stderr.write(f"Error: Invalid invariants format in issue {issue_id}\n")
            sys.exit(EXIT_CORRUPT_INPUT)

        processed_invariants = []
        sorted_invariants = sorted(invariants_raw, key=lambda x: str(x.get("invariant_id", "")))

        for inv in sorted_invariants:
            inv_id = str(inv.get("invariant_id", "UNKNOWN"))
            desc = str(inv.get("description", ""))
            test_ids = [str(t) for t in inv.get("test_ids", []) if isinstance(t, (str, int))]
            
            is_verified = len(test_ids) > 0
            total_invariants += 1
            if is_verified:
                covered_invariants += 1
            
            for t_id in test_ids:
                all_test_ids.add(t_id)

            processed_invariants.append({
                "invariant_id": inv_id,
                "description": desc,
                "test_ids": sorted(test_ids),
                "verified": is_verified
            })

        processed_items.append({
            "issue_id": issue_id,
            "title": title,
            "invariants": processed_invariants
        })

    total_issues = len(processed_items)
    total_tests = len(all_test_ids)
    coverage = (covered_invariants / total_invariants * 100.0) if total_invariants > 0 else 0.0

    status = "PASSED" if (total_invariants == covered_invariants) else "FAILED"

    report = {
        "version": "1.0.0",
        "timestamp": int(time.time()),
        "summary": {
            "total_issues": total_issues,
            "total_invariants": total_invariants,
            "total_tests": total_tests,
            "coverage_percentage": round(coverage, 2),
            "status": status
        },
        "items": processed_items
    }

    return report

def atomic_write(file_path, content):
    dir_name = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
        tf.write(content)
        temp_name = tf.name
    os.replace(temp_name, file_path)

def generate_human_readable(report):
    lines = []
    lines.append("=== LedgerLens Traceability Report ===")
    lines.append(f"Status: {report['summary']['status']}")
    lines.append(f"Coverage: {report['summary']['coverage_percentage']}%")
    lines.append(f"Total Issues: {report['summary']['total_issues']}")
    lines.append(f"Total Invariants: {report['summary']['total_invariants']}")
    lines.append(f"Total Tests Executed: {report['summary']['total_tests']}")
    lines.append("=" * 38)
    
    for item in report["items"]:
        lines.append(f"\nIssue [{item['issue_id']}]: {item['title']}")
        for inv in item["invariants"]:
            v_str = "VERIFIED" if inv["verified"] else "MISSING TEST"
            lines.append(f"  - Invariant [{inv['invariant_id']}]: {inv['description']} ({v_str})")
            for t_id in inv["test_ids"]:
                lines.append(f"      * Test: {t_id}")
    
    return "\n".join(lines) + "\n"

def main():
    args = parse_args()
    raw_data = validate_input_file(args.input)

    checkpoint_data = None
    if args.resume_checkpoint:
        if os.path.exists(args.resume_checkpoint):
            try:
                with open(args.resume_checkpoint, "r", encoding="utf-8") as cf:
                    checkpoint_data = json.load(cf)
            except Exception as e:
                sys.stderr.write(f"Error reading checkpoint: {str(e)}\n")
                sys.exit(EXIT_CHECKPOINT_ERROR)

    report = process_traceability(raw_data, checkpoint_data)

    if args.strict and report["summary"]["status"] != "PASSED":
        sys.stderr.write("Strict Mode Error: Traceability gaps found.\n")
        if not args.dry_run:
            if args.format == "json":
                out_str = json.dumps(report, indent=2, sort_keys=True)
            else:
                out_str = generate_human_readable(report)
            atomic_write(args.output, out_str)
        sys.exit(EXIT_TRACEABILITY_GAP)

    if args.dry_run:
        sys.stdout.write("Dry-run execution completed successfully. No files written.\n")
        sys.exit(EXIT_SUCCESS)

    if args.format == "json":
        output_content = json.dumps(report, indent=2, sort_keys=True)
    else:
        output_content = generate_human_readable(report)

    atomic_write(args.output, output_content)
    sys.exit(EXIT_SUCCESS)

if __name__ == "__main__":
    main()
