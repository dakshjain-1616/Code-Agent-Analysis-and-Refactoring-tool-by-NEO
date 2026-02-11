import os
import sys
import subprocess
import logging
import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    passed: bool
    total_tests: int
    failed_tests: int
    skipped_tests: int
    errors: List[str]
    coverage_percent: Optional[float] = None
    stdout: str = ""
    stderr: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "total_tests": self.total_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
            "coverage_percent": self.coverage_percent,
            "errors": self.errors
        }


class TestRunner:
    def __init__(self, config: Dict):
        self.config = config
        self.test_config = config.get("testing", {})
        self.framework = self.test_config.get("framework", "pytest")
        self.timeout = self.test_config.get("timeout", 300)
        self.coverage_threshold = self.test_config.get("coverage_threshold", 80)
        self.fail_on_test_failure = self.test_config.get("fail_on_test_failure", True)
    
    def discover_tests(self, directory: str) -> List[str]:
        test_files = []
        test_dir = Path(directory) / "tests"
        
        if not test_dir.exists():
            logger.warning(f"Test directory not found: {test_dir}")
            return test_files
        
        for file in test_dir.rglob("test_*.py"):
            test_files.append(str(file))
        
        for file in test_dir.rglob("*_test.py"):
            test_files.append(str(file))
        
        logger.info(f"Discovered {len(test_files)} test file(s)")
        return test_files
    
    def run_tests(self, directory: str, test_path: Optional[str] = None) -> TestResult:
        if self.framework == "pytest":
            return self._run_pytest(directory, test_path)
        elif self.framework == "unittest":
            return self._run_unittest(directory, test_path)
        else:
            logger.error(f"Unsupported test framework: {self.framework}")
            return TestResult(
                passed=False,
                total_tests=0,
                failed_tests=0,
                skipped_tests=0,
                errors=[f"Unsupported framework: {self.framework}"]
            )
    
    def _run_pytest(self, directory: str, test_path: Optional[str] = None) -> TestResult:
        try:
            cmd = ["pytest"]
            
            if test_path:
                cmd.append(test_path)
            else:
                test_dir = Path(directory) / "tests"
                if test_dir.exists():
                    cmd.append(str(test_dir))
                else:
                    logger.warning("No tests directory found, skipping tests")
                    return TestResult(
                        passed=True,
                        total_tests=0,
                        failed_tests=0,
                        skipped_tests=0,
                        errors=[],
                        stdout="No tests found"
                    )
            
            cmd.extend([
                "-v",
                "--tb=short",
                "--cov=" + directory,
                "--cov-report=json",
                "--cov-report=term",
                "--json-report",
                "--json-report-file=/tmp/pytest_report.json"
            ])
            
            result = subprocess.run(
                cmd,
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            stdout = result.stdout
            stderr = result.stderr
            
            total_tests = 0
            failed_tests = 0
            skipped_tests = 0
            errors = []
            coverage_percent = None
            
            try:
                if os.path.exists("/tmp/pytest_report.json"):
                    with open("/tmp/pytest_report.json", "r") as f:
                        report = json.load(f)
                        summary = report.get("summary", {})
                        total_tests = summary.get("total", 0)
                        failed_tests = summary.get("failed", 0)
                        skipped_tests = summary.get("skipped", 0)
            except Exception as e:
                logger.warning(f"Could not parse pytest JSON report: {e}")
            
            try:
                cov_file = Path(directory) / "coverage.json"
                if cov_file.exists():
                    with open(cov_file, "r") as f:
                        cov_data = json.load(f)
                        coverage_percent = cov_data.get("totals", {}).get("percent_covered")
            except Exception as e:
                logger.warning(f"Could not parse coverage report: {e}")
            
            if result.returncode != 0:
                for line in stderr.split('\n'):
                    if 'FAILED' in line or 'ERROR' in line:
                        errors.append(line.strip())
            
            passed = result.returncode == 0
            
            logger.info(f"Test run completed: {total_tests} total, {failed_tests} failed, {skipped_tests} skipped")
            
            return TestResult(
                passed=passed,
                total_tests=total_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                errors=errors,
                coverage_percent=coverage_percent,
                stdout=stdout,
                stderr=stderr
            )
            
        except subprocess.TimeoutExpired:
            logger.error(f"Test execution timed out after {self.timeout}s")
            return TestResult(
                passed=False,
                total_tests=0,
                failed_tests=0,
                skipped_tests=0,
                errors=[f"Test execution timed out after {self.timeout}s"]
            )
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return TestResult(
                passed=False,
                total_tests=0,
                failed_tests=0,
                skipped_tests=0,
                errors=[str(e)]
            )
    
    def _run_unittest(self, directory: str, test_path: Optional[str] = None) -> TestResult:
        try:
            cmd = [sys.executable, "-m", "unittest"]
            
            if test_path:
                cmd.append(test_path)
            else:
                cmd.append("discover")
                cmd.extend(["-s", str(Path(directory) / "tests"), "-p", "test_*.py"])
            
            cmd.append("-v")
            
            result = subprocess.run(
                cmd,
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            stdout = result.stdout
            stderr = result.stderr
            
            total_tests = stdout.count("test_")
            failed_tests = stdout.count("FAIL") + stdout.count("ERROR")
            skipped_tests = stdout.count("SKIP")
            
            errors = []
            for line in stderr.split('\n'):
                if 'FAIL' in line or 'ERROR' in line:
                    errors.append(line.strip())
            
            passed = result.returncode == 0
            
            return TestResult(
                passed=passed,
                total_tests=total_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                errors=errors,
                stdout=stdout,
                stderr=stderr
            )
            
        except Exception as e:
            logger.error(f"Unittest execution failed: {e}")
            return TestResult(
                passed=False,
                total_tests=0,
                failed_tests=0,
                skipped_tests=0,
                errors=[str(e)]
            )