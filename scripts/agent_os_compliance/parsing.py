from __future__ import annotations

import re
from dataclasses import dataclass


TASK_ID = re.compile(r"^(?:E\d+(?:\.\d+)*|DOC-\d+|LEGACY-\d+)$")
TASK_ID_PREFIX = re.compile(r"^(?:E\d+(?:\.\d+)*|DOC-\d+|LEGACY-\d+)")
DEPENDENCY_ID = re.compile(r"(?:E\d+(?:\.\d+)*|DOC-\d+|LEGACY-\d+|B-\d+)")


@dataclass(frozen=True)
class Task:
    task_id: str
    status: str
    priority: str
    dependencies: tuple[str, ...]
    definition: str
    line: int

    @property
    def complete(self) -> bool:
        return "[x]" in self.status.lower()

    @property
    def blocked(self) -> bool:
        return "[!]" in self.status.lower()

    @property
    def active(self) -> bool:
        return "[-]" in self.status.lower()


def _expand_range(value: str) -> list[str]:
    match = re.fullmatch(r"E(\d+)(?:\.(\d+))?-E(\d+)(?:\.(\d+))?", value)
    if not match:
        return [value]
    left_epic, left_task, right_epic, right_task = match.groups()
    if left_task is None and right_task is None:
        return [f"E{number}" for number in range(int(left_epic), int(right_epic) + 1)]
    if left_epic == right_epic and left_task is not None and right_task is not None:
        return [
            f"E{left_epic}.{number}"
            for number in range(int(left_task), int(right_task) + 1)
        ]
    return [value]


def dependencies(value: str) -> tuple[str, ...]:
    found: list[str] = []
    range_pattern = re.compile(r"E\d+(?:\.\d+)?-E\d+(?:\.\d+)?")
    ranges = range_pattern.findall(value)
    without_ranges = value
    for item in ranges:
        found.extend(_expand_range(item))
        without_ranges = without_ranges.replace(item, " ")
    found.extend(DEPENDENCY_ID.findall(without_ranges))
    return tuple(dict.fromkeys(found))


def parse_tasks(text: str) -> list[Task]:
    tasks: list[Task] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        task_match = next(
            ((index, TASK_ID_PREFIX.match(cell)) for index, cell in enumerate(cells) if TASK_ID_PREFIX.match(cell)),
            None,
        )
        if task_match is None:
            continue
        task_index, id_match = task_match
        tail = cells[task_index:]
        if len(tail) < 5:
            continue
        _, status, priority, deps, definition = tail[:5]
        task_id = id_match.group(0)
        tasks.append(
            Task(
                task_id=task_id,
                status=status,
                priority=priority,
                dependencies=dependencies(deps),
                definition=definition,
                line=line_number,
            )
        )
    return tasks


def active_task_from_current_state(text: str) -> str | None:
    section = re.search(
        r"(?ims)^## Current task\s+(.*?)(?=^## |\Z)",
        text,
    )
    if not section:
        return None
    match = DEPENDENCY_ID.search(section.group(1))
    return match.group(0) if match else None


@dataclass(frozen=True)
class ProgressEntry:
    date: str
    iteration: str
    body: str
    sections: dict[str, str]


def parse_progress(text: str) -> list[ProgressEntry]:
    matches = list(
        re.finditer(
            r"(?m)^## (\d{4}-\d{2}-\d{2})\s+[—-]\s+Iteration\s+([^\n]+)$",
            text,
        )
    )
    entries: list[ProgressEntry] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        sections: dict[str, str] = {}
        headings = list(re.finditer(r"(?m)^### (.+)$", body))
        for section_index, heading in enumerate(headings):
            section_end = (
                headings[section_index + 1].start()
                if section_index + 1 < len(headings)
                else len(body)
            )
            sections[heading.group(1).strip()] = body[heading.end() : section_end].strip()
        entries.append(
            ProgressEntry(match.group(1), match.group(2).strip(), body.strip(), sections)
        )
    return entries


@dataclass(frozen=True)
class Blocker:
    blocker_id: str
    fields: dict[str, str]
    line: int


def parse_blockers(text: str) -> list[Blocker]:
    matches = list(re.finditer(r"(?m)^## (B-\d+)\s+[—-]\s+(.+)$", text))
    result: list[Blocker] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        fields: dict[str, str] = {"Title": match.group(2).strip()}
        for field in re.finditer(r"(?m)^-\s+\*\*(.+?):\*\*\s*(.+)$", body):
            fields[field.group(1).strip()] = field.group(2).strip()
        result.append(Blocker(match.group(1), fields, text[: match.start()].count("\n") + 1))
    return result
