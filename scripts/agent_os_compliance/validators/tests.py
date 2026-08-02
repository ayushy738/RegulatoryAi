from __future__ import annotations

import subprocess
import sys

from ..models import ComplianceContext, Finding, Severity
from .base import Validator


class TestExecutionValidator(Validator):
    name = "test-execution"

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def validate(self, context: ComplianceContext) -> list[Finding]:
        if not self.enabled:
            return [Finding(self.name, Severity.WARNING, "Repository test execution was not requested.", suggestion="Run with --run-tests before merge.")]
        findings: list[Finding] = []
        for item in context.config.test_commands:
            command = item.command
            if command == "python" or command.startswith("python "):
                command = f'"{sys.executable}"{command[6:]}'
            result = subprocess.run(command, cwd=context.root / item.cwd, shell=True, text=True, capture_output=True, check=False)
            if result.returncode:
                output = (result.stdout + "\n" + result.stderr).strip()[-3000:]
                findings.append(Finding(self.name, Severity.ERROR, f"{item.category} command failed: {item.name}\n{output}"))
        return findings
