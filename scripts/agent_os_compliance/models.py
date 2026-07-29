from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    message: str
    files: tuple[str, ...] = ()
    suggestion: str = ""


@dataclass
class TestCommand:
    name: str
    category: str
    cwd: str
    command: str


@dataclass
class ComplianceConfig:
    root: Path
    raw: dict[str, Any]
    path: str

    @property
    def documents(self) -> dict[str, str]:
        return dict(self.raw.get("documents", {}))

    @property
    def frozen_files(self) -> dict[str, str]:
        return dict(self.raw.get("frozen_files", {}))

    @property
    def required_files(self) -> list[str]:
        return list(self.raw.get("required_files", []))

    @property
    def test_commands(self) -> list[TestCommand]:
        return [TestCommand(**item) for item in self.raw.get("test_commands", [])]


@dataclass
class ComplianceContext:
    root: Path
    config: ComplianceConfig
    base: str | None
    head: str
    changed_files: set[str]
    branch: str
    event_name: str = ""
    event_path: str = ""
    is_bootstrap: bool = False

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def exists(self, relative: str) -> bool:
        return (self.root / relative).exists()


@dataclass
class ComplianceReport:
    findings: list[Finding] = field(default_factory=list)
    validator_results: dict[str, bool] = field(default_factory=dict)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def errors(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == Severity.WARNING]

    @property
    def passed(self) -> bool:
        return not self.errors
