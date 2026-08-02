from __future__ import annotations

from pathlib import Path

from .models import ComplianceReport, Finding, Severity


def _icon(severity: Severity) -> str:
    return {Severity.ERROR: "FAIL", Severity.WARNING: "WARN", Severity.INFO: "PASS"}[severity]


def render_console(report: ComplianceReport) -> str:
    lines = ["", "AGENT OS COMPLIANCE REPORT", "=" * 72]
    for name, passed in sorted(report.validator_results.items()):
        lines.append(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if report.findings:
        lines.extend(["", "FINDINGS", "-" * 72])
    for finding in report.findings:
        lines.append(f"[{_icon(finding.severity)}] {finding.rule}: {finding.message}")
        if finding.files:
            lines.append(f"  Files: {', '.join(finding.files)}")
        if finding.suggestion:
            lines.append(f"  Fix: {finding.suggestion}")
    lines.extend(
        [
            "",
            f"Summary: {len(report.errors)} failure(s), {len(report.warnings)} warning(s)",
            f"Result: {'PASS' if report.passed else 'FAIL'}",
        ]
    )
    return "\n".join(lines)


def render_markdown(report: ComplianceReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        "# Agent OS Compliance Report",
        "",
        f"**Result:** {status}",
        "",
        "## Validator summary",
        "",
        "| Validator | Result |",
        "|---|---|",
    ]
    lines.extend(
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in sorted(report.validator_results.items())
    )
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No violations or warnings.")
    for item in report.findings:
        lines.extend(
            [
                f"### {_icon(item.severity)} — {item.rule}",
                "",
                item.message,
                "",
                f"- **Affected files:** {', '.join(item.files) if item.files else 'None'}",
                f"- **Suggested fix:** {item.suggestion or 'None'}",
                "",
            ]
        )
    return "\n".join(lines)


def write_report(report: ComplianceReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
