from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import ComplianceConfig, ComplianceContext


def _git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def resolve_base(root: Path, requested: str | None) -> str | None:
    candidate = requested or os.getenv("GITHUB_BASE_SHA")
    if candidate and set(candidate) != {"0"}:
        return candidate
    parent = _git(root, "rev-parse", "--verify", "HEAD~1", check=False)
    return parent or None


def build_context(
    root: Path,
    config: ComplianceConfig,
    *,
    base: str | None = None,
    head: str = "HEAD",
) -> ComplianceContext:
    resolved_base = resolve_base(root, base)
    changed: set[str] = set()
    if resolved_base:
        output = _git(root, "diff", "--name-only", f"{resolved_base}...{head}", check=False)
        changed.update(line for line in output.splitlines() if line)
    status = _git(root, "status", "--porcelain", check=False)
    for line in status.splitlines():
        if len(line) > 3:
            path = line[3:].replace("\\", "/")
            if not path.endswith("/"):
                changed.add(path)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", check=False)
    changed.update(line for line in untracked.splitlines() if line)
    branch = os.getenv("GITHUB_HEAD_REF") or _git(root, "branch", "--show-current", check=False)
    bootstrap = False
    if resolved_base:
        existing_config = _git(root, "show", f"{resolved_base}:{config.path}", check=False)
        bootstrap = not bool(existing_config)
    return ComplianceContext(
        root=root,
        config=config,
        base=resolved_base,
        head=head,
        changed_files=changed,
        branch=branch,
        event_name=os.getenv("GITHUB_EVENT_NAME", ""),
        event_path=os.getenv("GITHUB_EVENT_PATH", ""),
        is_bootstrap=bootstrap,
    )


def tracked_files(root: Path) -> list[str]:
    output = _git(root, "ls-files", "-co", "--exclude-standard", check=False)
    return sorted(set(line for line in output.splitlines() if line))


def commits(root: Path, base: str | None, head: str) -> list[str]:
    if not base:
        return []
    output = _git(root, "log", "--format=%s", f"{base}..{head}", check=False)
    return [line for line in output.splitlines() if line]
