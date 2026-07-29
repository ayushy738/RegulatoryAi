from __future__ import annotations

import re

from ..models import ComplianceContext, Finding, Severity
from .base import Validator


class DocumentationIntegrityValidator(Validator):
    name = "documentation-integrity"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        findings: list[Finding] = []
        for path in context.config.required_files:
            target = context.root / path
            if not target.is_file() or not target.read_text(encoding="utf-8").strip():
                findings.append(Finding(self.name, Severity.ERROR, "Required document missing or empty.", (path,)))
        for path, sections in context.config.raw.get("required_sections", {}).items():
            if not context.exists(path):
                continue
            text = context.read(path).lower()
            for section in sections:
                if section.lower() not in text:
                    findings.append(
                        Finding(self.name, Severity.ERROR, f"Required section missing: {section}", (path,))
                    )
        for path in context.config.required_files:
            if not path.endswith(".md") or not context.exists(path):
                continue
            text = context.read(path)
            for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
                link = match.group(1).split("#", 1)[0]
                if not link or "://" in link or link.startswith("#"):
                    continue
                target = ((context.root / path).parent / link).resolve()
                if not target.exists():
                    findings.append(
                        Finding(self.name, Severity.ERROR, f"Broken internal link: {link}", (path,))
                    )
        return findings
