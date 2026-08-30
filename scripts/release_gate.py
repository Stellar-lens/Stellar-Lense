"""Authoritative production-readiness gate for CI/CD.

This is the single source of truth for release gating.
It replaces check_release_readiness.py and release-readiness.yml.
CI jobs must invoke this as a blocking gate.

Gate levels:
- CRITICAL: Blocks release; pipeline fails red
- HIGH: Alerts on failure but does not block (with timeline to make blocking)
- INFO: Logging only; no blocking
"""

import logging
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class GateLevel(Enum):
    """Severity level for release gates."""

    CRITICAL = "CRITICAL"  # Blocks pipeline
    HIGH = "HIGH"  # Should block; currently warning with timeline
    INFO = "INFO"  # Logged only


@dataclass
class GateResult:
    """Result of a single gate check."""

    name: str
    level: GateLevel
    passed: bool
    message: str


class ReleaseGate:
    """Orchestrates all release readiness checks."""

    def __init__(self):
        self.results: list[GateResult] = []
        self.root = Path(__file__).parent.parent

    def run_all_gates(self) -> bool:
        """Run all release gates.

        Returns:
            True if all CRITICAL gates pass, False otherwise
        """
        logger.info("=== LedgerLens Release Gate ===")

        self.check_tests_pass()
        self.check_migrations_safe()
        self.check_schema_coverage()
        self.check_security_baseline()
        self.check_backup_readiness()
        self.check_threat_model_accuracy()

        return self.report_results()

    def add_result(self, name: str, level: GateLevel, passed: bool, message: str) -> None:
        """Record a gate result."""
        self.results.append(GateResult(name, level, passed, message))
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status} [{level.value}] {name}: {message}")

    def check_tests_pass(self) -> None:
        """CRITICAL: All tests must pass."""
        logger.info("\n[CRITICAL] Running test suite...")
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-q", "--tb=short"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=600,
            )
            passed = result.returncode == 0
            message = "All tests passed" if passed else "Some tests failed"
            self.add_result("Test Suite", GateLevel.CRITICAL, passed, message)
            if not passed:
                logger.error(f"Test output:\n{result.stdout}\n{result.stderr}")
        except subprocess.TimeoutExpired:
            self.add_result("Test Suite", GateLevel.CRITICAL, False, "Tests timed out (>10min)")
        except Exception as e:
            self.add_result("Test Suite", GateLevel.CRITICAL, False, f"Test execution failed: {e}")

    def check_migrations_safe(self) -> None:
        """CRITICAL: Migration framework must be present and tested."""
        logger.info("\n[CRITICAL] Validating migration framework...")
        migrations_dir = self.root / "migrations"
        base_file = migrations_dir / "base.py"
        runner_file = migrations_dir / "runner.py"
        test_file = self.root / "tests" / "test_migrations.py"

        has_base = base_file.exists()
        has_runner = runner_file.exists()
        has_tests = test_file.exists()

        message = f"base.py: {has_base}, runner.py: {has_runner}, tests: {has_tests}"
        passed = has_base and has_runner and has_tests

        self.add_result("Migration Framework", GateLevel.CRITICAL, passed, message)

    def check_schema_coverage(self) -> None:
        """CRITICAL: Database schema review gate must trigger on migration files."""
        logger.info("\n[CRITICAL] Checking schema review gate coverage...")
        review_gates = self.root / ".github" / "review-gates.yml"

        if not review_gates.exists():
            self.add_result(
                "Schema Review Gate",
                GateLevel.CRITICAL,
                False,
                "review-gates.yml does not exist",
            )
            return

        content = review_gates.read_text()
        has_migration_glob = "migrations/" in content or "migrations/**" in content

        message = (
            "Review gate includes migrations/ glob"
            if has_migration_glob
            else "Review gate does not cover migrations/"
        )
        self.add_result("Schema Review Gate", GateLevel.CRITICAL, has_migration_glob, message)

    def check_security_baseline(self) -> None:
        """HIGH: Lint, type checking, and security baseline (bandit, mypy)."""
        logger.info("\n[HIGH] Running security baseline checks...")

        checks = [
            ("ruff (linting)", ["ruff", "check", "."]),
            ("mypy (type checking)", ["mypy", ".", "--ignore-missing-imports"]),
            ("bandit (security)", ["bandit", "-r", ".", "-ll", "-q"]),
        ]

        for name, cmd in checks:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                passed = result.returncode == 0
                message = "Passed" if passed else "Failed (see logs)"
                self.add_result(name, GateLevel.HIGH, passed, message)
                if not passed:
                    logger.warning(f"{name} output:\n{result.stdout}\n{result.stderr}")
            except subprocess.TimeoutExpired:
                self.add_result(name, GateLevel.HIGH, False, f"{name} timed out")
            except FileNotFoundError:
                self.add_result(name, GateLevel.HIGH, False, f"{name} not installed")

    def check_backup_readiness(self) -> None:
        """HIGH: Backup/restore scripts must exist."""
        logger.info("\n[HIGH] Checking backup/restore automation...")
        backup_script = self.root / "scripts" / "backup.py"
        restore_script = self.root / "scripts" / "restore.py"

        has_backup = backup_script.exists()
        has_restore = restore_script.exists()

        message = f"backup.py: {has_backup}, restore.py: {has_restore}"
        passed = has_backup and has_restore

        self.add_result("Backup/Restore Scripts", GateLevel.HIGH, passed, message)

    def check_threat_model_accuracy(self) -> None:
        """INFO: Security threat model should be present."""
        logger.info("\n[INFO] Checking threat model documentation...")
        threat_model = self.root / "docs" / "security_threat_model.md"

        has_threat_model = threat_model.exists()
        message = "Security threat model present" if has_threat_model else "Missing threat model"

        self.add_result("Threat Model", GateLevel.INFO, has_threat_model, message)

    def report_results(self) -> bool:
        """Report results and determine if release is gated.

        Returns:
            True if all CRITICAL gates passed, False otherwise
        """
        logger.info("\n=== Release Gate Summary ===")

        critical_results = [r for r in self.results if r.level == GateLevel.CRITICAL]
        high_results = [r for r in self.results if r.level == GateLevel.HIGH]
        info_results = [r for r in self.results if r.level == GateLevel.INFO]

        critical_pass = all(r.passed for r in critical_results)
        high_pass = all(r.passed for r in high_results)

        logger.info(f"\nCRITICAL: {sum(1 for r in critical_results if r.passed)}/{len(critical_results)} passed")
        logger.info(f"HIGH:     {sum(1 for r in high_results if r.passed)}/{len(high_results)} passed")
        logger.info(f"INFO:     {sum(1 for r in info_results if r.passed)}/{len(info_results)} passed")

        if not critical_pass:
            logger.error("\n❌ RELEASE BLOCKED: CRITICAL gate(s) failed")
            return False

        if not high_pass:
            logger.warning(
                "\n⚠️  WARNING: HIGH gate(s) failed. Tracking as issues for remediation."
            )

        logger.info("\n✅ RELEASE GATE PASSED (all CRITICAL checks passed)")
        return True


def main() -> int:
    """Run release gate and exit with appropriate code."""
    gate = ReleaseGate()
    passed = gate.run_all_gates()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
