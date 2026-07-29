from __future__ import annotations

import re

from ..git import tracked_files
from ..models import ComplianceContext, Finding, Severity
from .base import Validator


PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[psoru]_[A-Za-z0-9_]{30,}\b"),
    "API token assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\b\s*[:=]\s*['\"][^'\"]{12,}['\"]"
    ),
}


class SecurityValidator(Validator):
    name = "security"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        findings: list[Finding] = []
        for path in tracked_files(context.root):
            normalized_path = f"/{path.replace(chr(92), '/')}"
            is_test_fixture = "/tests/" in normalized_path
            target = context.root / path
            if not target.is_file() or target.stat().st_size > 1_000_000:
                continue
            try:
                text = target.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for label, pattern in PATTERNS.items():
                # Generic assignments are common synthetic fixtures. High-signal
                # provider keys and private keys are still scanned in test files.
                if is_test_fixture and label == "API token assignment":
                    continue
                if pattern.search(text):
                    findings.append(
                        Finding(self.name, Severity.ERROR, f"Possible committed {label}.", (path,), "Remove and rotate the credential; use environment/secret storage.")
                    )
        return findings
