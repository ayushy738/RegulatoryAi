from __future__ import annotations

from collections import Counter

from ..models import ComplianceContext, Finding, Severity
from ..parsing import Task, parse_tasks
from .base import Validator


def _epic_satisfied(epic: str, tasks: dict[str, Task]) -> bool:
    children = [task for task_id, task in tasks.items() if task_id.startswith(f"{epic}.")]
    return bool(children) and all(task.complete for task in children)


class TaskValidator(Validator):
    name = "task-dependencies"

    def validate(self, context: ComplianceContext) -> list[Finding]:
        path = context.config.documents["tasks"]
        tasks_list = parse_tasks(context.read(path))
        tasks = {task.task_id: task for task in tasks_list}
        findings: list[Finding] = []
        duplicates = [item for item, count in Counter(t.task_id for t in tasks_list).items() if count > 1]
        for item in duplicates:
            findings.append(Finding(self.name, Severity.ERROR, f"Duplicate task ID: {item}", (path,)))
        graph: dict[str, list[str]] = {}
        for task in tasks_list:
            graph[task.task_id] = []
            if task.complete and task.blocked:
                findings.append(Finding(self.name, Severity.ERROR, f"Task is both complete and blocked: {task.task_id}", (path,)))
            parent = task.task_id.rsplit(".", 1)[0] if task.task_id.count(".") > 1 else None
            if parent and parent not in tasks:
                findings.append(Finding(self.name, Severity.ERROR, f"Orphan task {task.task_id}; parent {parent} missing.", (path,)))
            for dependency in task.dependencies:
                if dependency.startswith("B-"):
                    if task.complete:
                        findings.append(Finding(self.name, Severity.ERROR, f"Completed task {task.task_id} still depends on blocker {dependency}.", (path,)))
                    continue
                known = dependency in tasks or (dependency.startswith("E") and "." not in dependency and any(k.startswith(f"{dependency}.") for k in tasks))
                if not known:
                    findings.append(Finding(self.name, Severity.ERROR, f"Task {task.task_id} has orphan dependency {dependency}.", (path,)))
                    continue
                graph[task.task_id].append(dependency)
                satisfied = tasks[dependency].complete if dependency in tasks else _epic_satisfied(dependency, tasks)
                if task.complete and not satisfied:
                    findings.append(Finding(self.name, Severity.ERROR, f"Completed task {task.task_id} violates dependency {dependency}.", (path,)))
            if task.complete and ("TODO" in task.definition or "FIXME" in task.definition):
                findings.append(Finding(self.name, Severity.ERROR, f"Completed task {task.task_id} contains TODO/FIXME.", (path,)))
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                findings.append(Finding(self.name, Severity.ERROR, f"Circular task dependency includes {node}.", (path,)))
                return
            if node in visited:
                return
            visiting.add(node)
            for dep in graph.get(node, []):
                if dep in graph:
                    visit(dep)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)
        return findings
