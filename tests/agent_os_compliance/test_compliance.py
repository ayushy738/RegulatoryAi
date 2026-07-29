from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.agent_os_compliance.engine import ComplianceEngine
from scripts.agent_os_compliance.models import (
    ComplianceConfig,
    ComplianceContext,
    Finding,
    Severity,
)
from scripts.agent_os_compliance.validators.active_task import ActiveTaskValidator
from scripts.agent_os_compliance.validators.blockers import BlockerValidator
from scripts.agent_os_compliance.validators.docs import DocumentationIntegrityValidator
from scripts.agent_os_compliance.validators.frozen import FrozenDocumentationValidator
from scripts.agent_os_compliance.validators.progress import ProgressValidator
from scripts.agent_os_compliance.validators.security import SecurityValidator
from scripts.agent_os_compliance.validators.tasks import TaskValidator


def context(tmp_path: Path, raw: dict) -> ComplianceContext:
    config = ComplianceConfig(tmp_path, raw, ".agent-os-compliance.toml")
    return ComplianceContext(tmp_path, config, None, "HEAD", set(), "test/agent-os", is_bootstrap=True)


def write(tmp_path: Path, name: str, value: str) -> None:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def base_raw() -> dict:
    return {
        "required_files": ["docs/tasks.md", "docs/current.md", "docs/progress.md", "docs/blockers.md"],
        "required_sections": {},
        "documents": {
            "tasks": "docs/tasks.md", "current_state": "docs/current.md",
            "progress": "docs/progress.md", "blockers": "docs/blockers.md",
            "decisions": "docs/decisions.md", "changelog": "docs/changelog.md",
        },
        "frozen_files": {}, "frozen_approval_env": "ALLOW",
    }


def valid_repo(tmp_path: Path) -> ComplianceContext:
    raw = base_raw()
    write(tmp_path, "docs/tasks.md", "| Feature | Task | Status | Pri | Dependencies | Definition of Done |\n|---|---|---|---|---|---|\n| X | DOC-01 | [x] Complete | P0 | None | done |\n| X | E0.1 | [-] Active | P0 | DOC-01 | tested |")
    write(tmp_path, "docs/current.md", "## Current task\n**E0.1**")
    write(tmp_path, "docs/progress.md", "## 2026-01-01 — Iteration DOC-01\n### Work completed\nx\n### Files modified\nx\n### Tests executed\nx\n### Problems encountered\nnone\n### Next action\nE0.1")
    write(tmp_path, "docs/blockers.md", "# none")
    return context(tmp_path, raw)


def test_valid_repository(tmp_path: Path) -> None:
    ctx = valid_repo(tmp_path)
    validators = [DocumentationIntegrityValidator(), TaskValidator(), ActiveTaskValidator(), ProgressValidator(), BlockerValidator()]
    assert not [finding for validator in validators for finding in validator.validate(ctx)]


def test_terminal_blocked_repository_needs_no_active_task(tmp_path: Path) -> None:
    ctx = valid_repo(tmp_path)
    write(
        tmp_path,
        "docs/tasks.md",
        "| Feature | Task | Status | Pri | Dependencies | Definition of Done |\n"
        "|---|---|---|---|---|---|\n"
        "| X | DOC-01 | [x] Complete | P0 | None | done |\n"
        "| X | E0.1 | [!] Blocked | P0 | DOC-01,B-001 | tested |",
    )
    write(
        tmp_path,
        "docs/current.md",
        "## Current task\nNo dependency-eligible task remains.",
    )

    assert not ActiveTaskValidator().validate(ctx)


def test_missing_active_task_fails_when_eligible_work_remains(
    tmp_path: Path,
) -> None:
    ctx = valid_repo(tmp_path)
    write(
        tmp_path,
        "docs/tasks.md",
        "| Feature | Task | Status | Pri | Dependencies | Definition of Done |\n"
        "|---|---|---|---|---|---|\n"
        "| X | DOC-01 | [x] Complete | P0 | None | done |\n"
        "| X | E0.1 | [ ] Planned | P0 | DOC-01 | tested |",
    )
    write(
        tmp_path,
        "docs/current.md",
        "## Current task\nNo active task selected.",
    )

    findings = ActiveTaskValidator().validate(ctx)

    assert [finding.message for finding in findings] == [
        "CURRENT_STATE active task is missing from TASKS."
    ]


@pytest.mark.parametrize("missing", ["docs/tasks.md", "docs/current.md", "docs/progress.md"])
def test_missing_required_document(tmp_path: Path, missing: str) -> None:
    ctx = valid_repo(tmp_path)
    (tmp_path / missing).unlink()
    assert DocumentationIntegrityValidator().validate(ctx)


def test_broken_task_dependency(tmp_path: Path) -> None:
    ctx = valid_repo(tmp_path)
    write(tmp_path, "docs/tasks.md", "| F | E0.1 | [x] Complete | P0 | E9.9 | done |")
    assert TaskValidator().validate(ctx)


def test_modified_frozen_file(tmp_path: Path) -> None:
    write(tmp_path, "frozen.md", "approved")
    raw = base_raw()
    raw["frozen_files"] = {"frozen.md": hashlib.sha256(b"different").hexdigest()}
    ctx = context(tmp_path, raw)
    assert FrozenDocumentationValidator().validate(ctx)


def test_invalid_blocker(tmp_path: Path) -> None:
    ctx = valid_repo(tmp_path)
    write(tmp_path, "docs/blockers.md", "## B-001 — Bad\n- **Status:** Resolved")
    assert BlockerValidator().validate(ctx)


def test_security_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = valid_repo(tmp_path)
    write(tmp_path, "secret.py", 'api_key = "abcdefghijklmnop"')
    monkeypatch.setattr("scripts.agent_os_compliance.validators.security.tracked_files", lambda _: ["secret.py"])
    assert SecurityValidator().validate(ctx)


def test_engine_collects_all_violations_and_validator_crashes(tmp_path: Path) -> None:
    class Invalid:
        name = "invalid"

        def validate(self, _: ComplianceContext) -> list[Finding]:
            return [Finding(self.name, Severity.ERROR, "first violation")]

    class Crashed:
        name = "crashed"

        def validate(self, _: ComplianceContext) -> list[Finding]:
            raise RuntimeError("broken validator")

    engine = ComplianceEngine()
    engine.validators = [Invalid(), Crashed()]
    report = engine.run(context(tmp_path, base_raw()))

    assert [finding.rule for finding in report.errors] == ["invalid", "crashed"]
    assert report.validator_results == {"invalid": False, "crashed": False}
