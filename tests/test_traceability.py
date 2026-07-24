import unittest
import os
import subprocess
import json
import tempfile

class TestTraceabilityReport(unittest.TestCase):

    def setUp(self):
        self.script_path = os.path.join(os.path.dirname(__file__), "../tools/replay/traceability_report.py")
        self.fixture_path = os.path.join(os.path.dirname(__file__), "../tools/replay/fixtures/sample_matrix.json")
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, args):
        cmd = [self.script_path] + args
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_golden_path_json(self):
        out_path = os.path.join(self.temp_dir.name, "report.json")
        res = self.run_cli(["--input", self.fixture_path, "--output", out_path, "--format", "json"])
        self.assertEqual(res.returncode, 0)
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["summary"]["status"], "PASSED")
        self.assertEqual(data["summary"]["coverage_percentage"], 100.0)

    def test_golden_path_human(self):
        out_path = os.path.join(self.temp_dir.name, "report.txt")
        res = self.run_cli(["--input", self.fixture_path, "--output", out_path, "--format", "human"])
        self.assertEqual(res.returncode, 0)
        with open(out_path, "r") as f:
            text = f.read()
        self.assertIn("=== LedgerLens Traceability Report ===", text)
        self.assertIn("Status: PASSED", text)

    def test_corrupt_json_input(self):
        bad_input = os.path.join(self.temp_dir.name, "bad.json")
        with open(bad_input, "w") as f:
            f.write("{ invalid json structure")
        out_path = os.path.join(self.temp_dir.name, "report.json")
        res = self.run_cli(["--input", bad_input, "--output", out_path])
        self.assertEqual(res.returncode, 2)

    def test_dry_run_no_file_creation(self):
        out_path = os.path.join(self.temp_dir.name, "dry_run_output.json")
        res = self.run_cli(["--input", self.fixture_path, "--output", out_path, "--dry-run"])
        self.assertEqual(res.returncode, 0)
        self.assertFalse(os.path.exists(out_path))

    def test_strict_mode_failure(self):
        uncovered_fixture = os.path.join(self.temp_dir.name, "uncovered.json")
        data = [
            {
                "issue_id": "LL-200",
                "title": "Uncovered Invariant Test",
                "invariants": [
                    {
                        "invariant_id": "INV-99",
                        "description": "No test associated",
                        "test_ids": []
                    }
                ]
            }
        ]
        with open(uncovered_fixture, "w") as f:
            json.dump(data, f)

        out_path = os.path.join(self.temp_dir.name, "strict_report.json")
        res = self.run_cli(["--input", uncovered_fixture, "--output", out_path, "--strict"])
        self.assertEqual(res.returncode, 3)

if __name__ == "__main__":
    unittest.main()
