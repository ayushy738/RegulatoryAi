from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend.core.intelligence_repository import (
    intelligence_readiness_report,
    list_intelligence_deadlines,
    list_obligation_groups,
    list_stakeholder_intelligence,
)

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP20_REGULATORY_INTELLIGENCE_EXPERIENCE.md")


def main() -> None:
    active_deadlines = list_intelligence_deadlines(status="active", limit=20)
    all_deadlines = list_intelligence_deadlines(status="all", limit=500)
    obligations = list_obligation_groups(limit=80)
    stakeholders = list_stakeholder_intelligence()
    readiness = intelligence_readiness_report()
    report = _markdown_report(
        active_deadlines=active_deadlines,
        all_deadlines=all_deadlines,
        obligations=obligations,
        stakeholders=stakeholders,
        readiness=readiness,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


def _markdown_report(
    *,
    active_deadlines,
    all_deadlines,
    obligations,
    stakeholders,
    readiness,
) -> str:
    obligation_count = sum(len(group.obligations) for group in obligations)
    lines = [
        "# Step 20 Regulatory Intelligence Experience Layer",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## What Was Implemented",
        "",
        "- `GET /intelligence/deadlines`: active/historical/all graph deadline API with "
        "issuer, deadline-type, and stakeholder filters.",
        "- `GET /intelligence/obligations`: obligations grouped by stakeholder.",
        "- `GET /intelligence/stakeholders`: stakeholder intelligence cards for the "
        "supported power-sector stakeholder set.",
        "- `GET /intelligence/stakeholders/{stakeholder}`: one stakeholder intelligence view.",
        "- `GET /intelligence/readiness`: readiness snapshot over deadlines, obligations, "
        "regulatory impacts, and consultation tracking.",
        "- Frontend route `/intelligence`: deadlines center, obligations center, "
        "stakeholder intelligence, and readiness notes.",
        "",
        "## Current Data Snapshot",
        "",
        f"- Active future deadlines: {len(active_deadlines)}",
        f"- Extracted graph deadline/date rows: {len(all_deadlines)}",
        f"- Stakeholder obligation groups: {len(obligations)}",
        f"- Obligation rows shown in groups: {obligation_count}",
        f"- Stakeholder intelligence panels: {len(stakeholders)}",
        f"- Consultation tracking items: {len(readiness.consultation_tracking)}",
        f"- Readiness status: {readiness.status}",
        "",
        "## Active Deadlines",
        "",
    ]
    if active_deadlines:
        for deadline in active_deadlines[:10]:
            lines.append(
                f"- {deadline.deadline_type} on {deadline.deadline_date}: "
                f"{_clip(deadline.title, 120)} ({deadline.issuer or 'Unknown issuer'})"
            )
    else:
        lines.append(
            "- None. The active API is working, but the current graph has no future-dated "
            "deadline rows."
        )
    lines.extend(["", "## Extracted Deadline Examples", ""])
    for deadline in all_deadlines[:8]:
        lines.append(
            f"- {deadline.deadline_type} -> {deadline.deadline_date or deadline.raw_date}: "
            f"{_clip(deadline.title, 120)}"
        )
    lines.extend(["", "## Stakeholder Obligations", ""])
    if obligations:
        for group in obligations[:8]:
            top = group.obligations[0] if group.obligations else None
            lines.append(
                f"- {group.stakeholder}: {len(group.obligations)} obligation(s)"
                + (f"; example: {_clip(top.obligation, 130)}" if top else "")
            )
    else:
        lines.append("- None found.")
    lines.extend(["", "## Regulatory Impacts", ""])
    for stakeholder in stakeholders:
        lines.append(
            f"- {stakeholder.stakeholder}: "
            f"{stakeholder.counts.get('regulations', 0)} regulations, "
            f"{stakeholder.counts.get('obligations', 0)} obligations, "
            f"{stakeholder.counts.get('deadlines', 0)} deadlines, "
            f"{stakeholder.counts.get('tenders', 0)} tenders."
        )
    lines.extend(["", "## Consultation Tracking", ""])
    if readiness.consultation_tracking:
        for item in readiness.consultation_tracking[:8]:
            lines.append(f"- {_clip(item.title, 140)} ({item.issuer or 'Unknown issuer'})")
    else:
        lines.append(
            "- None. No accepted primary consultation documents exist in the current graph."
        )
    lines.extend(
        [
            "",
            "## Can A User Answer The Core Questions?",
            "",
            "- What do I need to do? **Partially yes.** The obligations center exposes "
            "actionable graph obligations, especially around transmission/tender documents.",
            "- What deadlines matter? **Partially.** The deadline center exposes graph dates, "
            "but the current corpus has no future active deadlines.",
            "- What affects my organization? **Partially yes.** Stakeholder panels summarize "
            "regulations, obligations, deadlines, and tenders by stakeholder, but coverage "
            "depends on more accepted primary documents.",
            "",
            "## Readiness Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in readiness.notes)
    lines.extend(
        [
            "",
            "## Assessment",
            "",
            "Choice: **PARTIALLY READY**.",
            "",
            "The platform now has a real user-facing intelligence layer over the knowledge "
            "graph. It is useful for obligations and stakeholder impact scanning. It is not "
            "yet a complete regulatory intelligence product because active consultations and "
            "future deadlines are absent from the current graph data.",
        ]
    )
    return "\n".join(lines)


def _clip(value: object, limit: int = 180) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit].rstrip() + "..."


if __name__ == "__main__":
    main()
