from __future__ import annotations

from ..models import ComplianceContext, Finding, Severity
from ..parsing import active_task_from_current_state, parse_tasks
from .base import Validator
from .tasks import _epic_satisfied


class ActiveTaskValidator(Validator):
    name = "active-task"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        task_path = context.config.documents["tasks"]
        current_path = context.config.documents["current_state"]
        tasks = parse_tasks(context.read(task_path))
        by_id = {task.task_id: task for task in tasks}
        active_id = active_task_from_current_state(context.read(current_path))
        findings: list[Finding] = []
        eligible = [task for task in tasks if not task.complete and not task.blocked and all(
            (dep in by_id and by_id[dep].complete) or
            (dep.startswith("E") and "." not in dep and _epic_satisfied(dep, by_id))
            for dep in task.dependencies if not dep.startswith("B-")
        )]
        active_markers = [task.task_id for task in tasks if task.active]
        if not active_id:
            if eligible:
                findings.append(Finding(
                    self.name,
                    Severity.ERROR,
                    "CURRENT_STATE active task is missing from TASKS.",
                    (current_path, task_path),
                ))
            if active_markers:
                findings.append(Finding(
                    self.name,
                    Severity.ERROR,
                    f"TASKS active marker mismatch: {active_markers}.",
                    (task_path,),
                ))
            return findings
        if active_id not in by_id:
            return [Finding(self.name, Severity.ERROR, "CURRENT_STATE active task is missing from TASKS.", (current_path, task_path))]
        active = by_id[active_id]
        if active.complete or active.blocked:
            findings.append(Finding(self.name, Severity.ERROR, f"Active task {active_id} is complete or blocked.", (current_path, task_path)))
        if active_markers != [active_id]:
            findings.append(Finding(self.name, Severity.ERROR, f"TASKS active marker mismatch: {active_markers}.", (task_path,)))
        for dep in active.dependencies:
            if dep.startswith("B-"):
                findings.append(Finding(self.name, Severity.ERROR, f"Active task depends on unresolved blocker {dep}.", (task_path,)))
            elif dep in by_id and not by_id[dep].complete:
                findings.append(Finding(self.name, Severity.ERROR, f"Active task dependency incomplete: {dep}.", (task_path,)))
            elif dep.startswith("E") and "." not in dep and not _epic_satisfied(dep, by_id):
                findings.append(Finding(self.name, Severity.ERROR, f"Active task epic dependency incomplete: {dep}.", (task_path,)))
        if eligible:
            priority = min(int(task.priority[1:]) for task in eligible if task.priority.startswith("P"))
            first = next(task for task in eligible if task.priority == f"P{priority}")
            if first.task_id != active_id:
                findings.append(Finding(self.name, Severity.ERROR, f"Active task {active_id} is not first eligible task {first.task_id}.", (current_path, task_path)))
        return findings
