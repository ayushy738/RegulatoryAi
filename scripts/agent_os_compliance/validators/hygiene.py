from __future__ import annotations

import re
from fnmatch import fnmatch

from ..models import ComplianceContext, Finding, Severity
from .base import Validator


class HygieneValidator(Validator):
    name = "repository-hygiene"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        findings: list[Finding] = []
        generated = context.config.raw.get("generated_artifact_patterns", [])
        for path in context.changed_files:
            if path.rstrip("/") == "artifacts":
                continue
            if any(fnmatch(path, pattern) for pattern in generated):
                findings.append(Finding(self.name, Severity.ERROR, "Generated/temporary artifact is part of the change.", (path,)))
            target = context.root / path
            if not target.is_file() or target.stat().st_size > 1_000_000:
                continue
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if re.search(r"(?m)^(<<<<<<< |=======|>>>>>>> )", text):
                findings.append(Finding(self.name, Severity.ERROR, "Merge conflict marker found.", (path,)))
            if path.startswith("apps/") and not any(token in path for token in ("/tests/", ".test.", ".spec.")):
                if re.search(r"\bconsole\.log\s*\(|\bbreakpoint\s*\(\s*\)", text):
                    findings.append(Finding(self.name, Severity.ERROR, "Debug statement found in application code.", (path,)))
        return findings
