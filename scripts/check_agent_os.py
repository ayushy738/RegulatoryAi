from __future__ import annotations

import argparse
from pathlib import Path

from agent_os_compliance.config import load_config
from agent_os_compliance.engine import ComplianceEngine
from agent_os_compliance.git import build_context
from agent_os_compliance.reporting import render_console, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Agent OS repository compliance")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=".agent-os-compliance.toml")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    config = load_config(root, args.config)
    context = build_context(root, config, base=args.base, head=args.head)
    report = ComplianceEngine(run_tests=args.run_tests).run(context)
    print(render_console(report))
    output = args.report or config.raw.get("report_path")
    if output:
        write_report(report, root / output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
