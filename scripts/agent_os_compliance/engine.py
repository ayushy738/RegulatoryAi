from __future__ import annotations

from .models import ComplianceContext, ComplianceReport, Severity
from .validators import (
    ActiveTaskValidator, BlockerValidator, BranchValidator, DocumentationIntegrityValidator,
    DocumentationSyncValidator, FrozenDocumentationValidator, HygieneValidator,
    ProgressValidator, SecurityValidator, TaskValidator, TestExecutionValidator,
)


class ComplianceEngine:
    def __init__(self, *, run_tests: bool = False) -> None:
        self.validators = [
            FrozenDocumentationValidator(), DocumentationIntegrityValidator(),
            DocumentationSyncValidator(), TaskValidator(), ActiveTaskValidator(),
            ProgressValidator(), BlockerValidator(), SecurityValidator(),
            HygieneValidator(), BranchValidator(), TestExecutionValidator(run_tests),
        ]

    def run(self, context: ComplianceContext) -> ComplianceReport:
        report = ComplianceReport()
        for validator in self.validators:
            try:
                findings = validator.validate(context)
            except Exception as exc:  # validator failures are compliance failures, not silent skips
                from .models import Finding
                findings = [Finding(validator.name, Severity.ERROR, f"Validator crashed: {exc}")]
            report.findings.extend(findings)
            report.validator_results[validator.name] = not any(item.severity == Severity.ERROR for item in findings)
        return report
