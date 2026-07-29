from __future__ import annotations

import json
import re
from fnmatch import fnmatch

from ..git import commits
from ..models import ComplianceContext, Finding, Severity
from .base import Validator


class BranchValidator(Validator):
    name = "branch-and-pr"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        findings: list[Finding] = []
        if context.branch and not any(fnmatch(context.branch, item) for item in context.config.raw.get("allowed_branches", [])):
            findings.append(Finding(self.name, Severity.ERROR, f"Branch name is not allowed: {context.branch}"))
        if context.event_name:
            pattern = re.compile(context.config.raw["commit_message_pattern"])
            for message in commits(context.root, context.base, context.head):
                if not pattern.match(message):
                    findings.append(Finding(self.name, Severity.ERROR, f"Noncompliant commit message: {message}", suggestion="Use Conventional Commit style."))
        if context.event_name == "pull_request" and context.event_path:
            event = json.loads((context.root / context.event_path).read_text(encoding="utf-8")) if not context.event_path.startswith("/") else json.loads(open(context.event_path, encoding="utf-8").read())
            pr = event.get("pull_request", {})
            if not pr.get("title", "").strip() or not pr.get("body", "").strip():
                findings.append(Finding(self.name, Severity.ERROR, "Pull request title and body are required."))
        return findings
