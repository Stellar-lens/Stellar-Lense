import os
import json
import time
import sys

def generate_report(matrix_path, schema_path, output_path):
    if not os.path.exists(matrix_path):
        print(f"Error: Matrix file not found at {matrix_path}")
        sys.exit(1)

    with open(matrix_path, "r") as f:
        matrix = json.load(f)

    total_issues = len(matrix)
    total_invariants = 0
    test_ids_set = set()
    verified_invariants = 0

    report_items = []

    for issue in matrix:
        issue_id = issue.get("issue_id", "")
        title = issue.get("title", "")
        invariants = issue.get("invariants", [])

        processed_invariants = []
        for inv in invariants:
            total_invariants += 1
            inv_id = inv.get("invariant_id", "")
            desc = inv.get("description", "")
            test_ids = inv.get("test_ids", [])
            
            for t_id in test_ids:
                test_ids_set.add(t_id)

            is_verified = len(test_ids) > 0
            if is_verified:
                verified_invariants += 1

            processed_invariants.append({
                "invariant_id": inv_id,
                "description": desc,
                "test_ids": test_ids,
                "verified": is_verified
            })

        report_items.append({
            "issue_id": issue_id,
            "title": title,
            "invariants": processed_invariants
        })

    total_tests = len(test_ids_set)
    coverage = (verified_invariants / total_invariants * 100.0) if total_invariants > 0 else 0.0

    status = "PASSED" if coverage == 100.0 else "INCOMPLETE"

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
        "items": report_items
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Report generated successfully at {output_path}")

if __name__ == "__main__":
    matrix_p = "tools/replay/fixtures/sample_matrix.json"
    schema_p = "tools/replay/schemas/traceability_v1.json"
    out_p = "tools/replay/reports/traceability_report.json"
    generate_report(matrix_p, schema_p, out_p)
