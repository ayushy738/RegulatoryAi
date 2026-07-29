from __future__ import annotations

from fnmatch import fnmatch

from ..models import ComplianceContext, Finding, Severity
from ..parsing import parse_tasks
from .base import Validator


def _matches(files: set[str], patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for path in files for pattern in patterns)


class DocumentationSyncValidator(Validator):
    name = "documentation-synchronization"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        changed = context.changed_files
        docs = context.config.documents
        findings: list[Finding] = []
        rules = []
        if _matches(changed, context.config.raw.get("application_patterns", [])):
            rules.append((docs["current_state"], "Application code changed; CURRENT_STATE must change."))
        if docs["current_state"] in changed:
            rules.append((docs["progress"], "CURRENT_STATE changed; PROGRESS must change."))
        if _matches(changed, context.config.raw.get("architecture_patterns", [])):
            rules.append((docs["decisions"], "Architecture/configuration changed; DECISIONS must change."))
        if _matches(changed, context.config.raw.get("public_behavior_patterns", [])):
            rules.append((docs["changelog"], "Public behavior changed; CHANGELOG must change."))
        for required, message in rules:
            if required not in changed and not context.is_bootstrap:
                findings.append(Finding(self.name, Severity.ERROR, message, (required,)))
        if context.base and docs["tasks"] in changed:
            # Completion changes require progress. The exact transition is checked when base content is available.
            if docs["progress"] not in changed and not context.is_bootstrap:
                findings.append(Finding(self.name, Severity.ERROR, "TASKS changed without a PROGRESS update.", (docs["tasks"], docs["progress"])))
        tasks = parse_tasks(context.read(docs["tasks"]))
        if any(task.blocked for task in tasks) and docs["blockers"] not in changed and docs["tasks"] in changed and not context.is_bootstrap:
            findings.append(Finding(self.name, Severity.ERROR, "Blocked task state changed without BLOCKERS update.", (docs["tasks"], docs["blockers"])))
        return findings
