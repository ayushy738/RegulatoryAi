from __future__ import annotations

import hashlib
import os

from ..models import ComplianceContext, Finding, Severity
from .base import Validator


class FrozenDocumentationValidator(Validator):
    name = "frozen-documentation"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        findings: list[Finding] = []
        approved = os.getenv(context.config.raw["frozen_approval_env"]) == "1"
        for path, expected in context.config.frozen_files.items():
            target = context.root / path
            if not target.is_file():
                findings.append(
                    Finding(self.name, Severity.ERROR, "Frozen file is missing.", (path,))
                )
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest().upper()
            if actual != expected.upper():
                findings.append(
                    Finding(
                        self.name,
                        Severity.ERROR,
                        "Frozen file hash does not match the approved configuration.",
                        (path,),
                        "Restore the file or use the separately approved frozen-update process.",
                    )
                )
            if path in context.changed_files and not (approved or context.is_bootstrap):
                findings.append(
                    Finding(
                        self.name,
                        Severity.ERROR,
                        "A frozen document changed in this diff.",
                        (path,),
                        "Revert it; approved updates require AGENT_OS_ALLOW_FROZEN_UPDATE=1.",
                    )
                )
        return findings
