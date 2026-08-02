from __future__ import annotations

from ..models import ComplianceContext, Finding, Severity
from ..parsing import parse_blockers
from .base import Validator


class BlockerValidator(Validator):
    name = "blockers"
    required = ("Description", "Severity", "Possible solutions", "Dependencies", "Owner", "Status")

    def validate(self, context: ComplianceContext) -> list[Finding]:
        path = context.config.documents["blockers"]
        blockers = parse_blockers(context.read(path))
        findings: list[Finding] = []
        seen: set[str] = set()
        for blocker in blockers:
            if blocker.blocker_id in seen:
                findings.append(Finding(self.name, Severity.ERROR, f"Duplicate blocker ID: {blocker.blocker_id}", (path,)))
            seen.add(blocker.blocker_id)
            missing = [field for field in self.required if not blocker.fields.get(field, "").strip()]
            if missing:
                findings.append(Finding(self.name, Severity.ERROR, f"{blocker.blocker_id} missing fields: {', '.join(missing)}", (path,)))
            status = blocker.fields.get("Status", "").lower().rstrip(".")
            if status in {"resolved", "closed", "complete", "completed"}:
                findings.append(Finding(self.name, Severity.ERROR, f"Resolved blocker {blocker.blocker_id} remains active.", (path,), "Remove it after recording resolution in Progress/Changelog."))
        return findings
