# Agent OS Compliance Framework

## Architecture

The framework is a Git-aware Python validator package under
`scripts/agent_os_compliance/`. Central policy lives in
`.agent-os-compliance.toml`. Each validator returns typed findings; the engine
runs every validator, collects all violations, prints one report, and returns a
single failing exit code.

Validators cover frozen hashes, documentation synchronization and integrity,
task dependencies, active task, progress, blockers, required test commands,
secrets, repository hygiene, branches, commits, and PR metadata.

## Run locally

Static validation:

```text
python scripts/check_agent_os.py
```

Full validation, including API/web tests, lint, typecheck, and build:

```text
python scripts/check_agent_os.py --run-tests
```

Compare a specific range:

```text
python scripts/check_agent_os.py --base <base-sha> --head <head-sha>
```

## Configuration

Edit `.agent-os-compliance.toml` to declare required/frozen documents, hashes,
required sections, synchronization triggers, branch policy, ignored generated
artifacts, and test commands. Frozen updates require both an approved hash
change and `AGENT_OS_ALLOW_FROZEN_UPDATE=1`.

## Add a rule

1. Add a `Validator` subclass in `scripts/agent_os_compliance/validators/`.
2. Return all findings; never raise for a normal violation.
3. Register it in `validators/__init__.py` and `ComplianceEngine`.
4. Add valid and invalid fixture tests.
5. Document configuration and suggested remediation.

## Interpret failures

Every finding includes severity, rule, affected files, and a suggested fix.
The console report is always complete. GitHub Actions also uploads
`agent-os-compliance-report.md`.

Validator crashes are converted into compliance failures so a broken rule can
never silently pass.

## Extension policy

Keep validators independent and side-effect free except the configured test
runner. Reuse parsing and Git helpers. Do not hardcode repository paths in
validators; add policy through the TOML configuration.
