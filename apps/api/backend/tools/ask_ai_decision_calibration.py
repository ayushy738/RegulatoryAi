from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.ask.decision import load_decision_calibration_dataset
from backend.ask.decision.calibration_evaluation import (
    evaluate_decision_calibration,
    file_sha256,
    load_entity_catalog,
    render_decision_calibration_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the approved B-013 Decision Engine golden dataset."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--entity-catalog", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-markdown", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    dataset = load_decision_calibration_dataset(args.dataset)
    report = evaluate_decision_calibration(
        dataset,
        entity_catalog=load_entity_catalog(args.entity_catalog),
        entity_registry_sha256=file_sha256(args.entity_catalog),
        code_revision=args.code_revision,
        environment=args.environment,
    )
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    args.report_markdown.write_text(
        render_decision_calibration_report(report),
        encoding="utf-8",
    )
    print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
    if not report.acceptance_passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
