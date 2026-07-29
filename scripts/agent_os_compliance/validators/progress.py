from __future__ import annotations

from datetime import date

from ..models import ComplianceContext, Finding, Severity
from ..parsing import parse_progress, parse_tasks
from .base import Validator


class ProgressValidator(Validator):
    name = "progress"
    required = ("Work completed", "Files modified", "Tests executed", "Problems encountered", "Next action")

    def validate(self, context: ComplianceContext) -> list[Finding]:
        path = context.config.documents["progress"]
        entries = parse_progress(context.read(path))
        findings: list[Finding] = []
        if not entries:
            return [Finding(self.name, Severity.ERROR, "No progress entries found.", (path,))]
        dates = [entry.date for entry in entries]
        if dates != sorted(dates):
            findings.append(Finding(self.name, Severity.ERROR, "Progress timestamps are not monotonic.", (path,)))
        if entries[-1].date > date.today().isoformat():
            findings.append(Finding(self.name, Severity.ERROR, "Latest progress entry is future-dated.", (path,)))
        for entry in entries:
            for section in self.required:
                if not entry.sections.get(section, "").strip():
                    findings.append(Finding(self.name, Severity.ERROR, f"Progress {entry.iteration} has empty/missing {section}.", (path,)))
        completed = {task.task_id for task in parse_tasks(context.read(context.config.documents["tasks"])) if task.complete}
        if entries[-1].iteration not in completed:
            findings.append(Finding(self.name, Severity.ERROR, f"Latest progress iteration {entries[-1].iteration} is not a completed task.", (path,)))
        return findings
