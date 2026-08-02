# Agent OS Compliance Report

**Result:** FAIL

## Validator summary

| Validator | Result |
|---|---|
| active-task | PASS |
| blockers | PASS |
| branch-and-pr | FAIL |
| documentation-integrity | PASS |
| documentation-synchronization | PASS |
| frozen-documentation | FAIL |
| progress | PASS |
| repository-hygiene | PASS |
| security | PASS |
| task-dependencies | PASS |
| test-execution | PASS |

## Findings

### FAIL — frozen-documentation

A frozen document changed in this diff.

- **Affected files:** docs/ASK_AI/ASK_AI_AUDIT.md
- **Suggested fix:** Revert it; approved updates require AGENT_OS_ALLOW_FROZEN_UPDATE=1.

### FAIL — frozen-documentation

A frozen document changed in this diff.

- **Affected files:** docs/ASK_AI/ASK_AI_PRODUCT_SPEC.md
- **Suggested fix:** Revert it; approved updates require AGENT_OS_ALLOW_FROZEN_UPDATE=1.

### FAIL — frozen-documentation

A frozen document changed in this diff.

- **Affected files:** docs/ASK_AI/ASK_AI_DECISION_ENGINE.md
- **Suggested fix:** Revert it; approved updates require AGENT_OS_ALLOW_FROZEN_UPDATE=1.

### FAIL — frozen-documentation

A frozen document changed in this diff.

- **Affected files:** docs/ASK_AI/ASK_AI_ORCHESTRATOR.md
- **Suggested fix:** Revert it; approved updates require AGENT_OS_ALLOW_FROZEN_UPDATE=1.

### FAIL — frozen-documentation

A frozen document changed in this diff.

- **Affected files:** docs/ASK_AI/ASK_AI_IMPLEMENTATION_PLAN.md
- **Suggested fix:** Revert it; approved updates require AGENT_OS_ALLOW_FROZEN_UPDATE=1.

### FAIL — branch-and-pr

Branch name is not allowed: ask-ai-review

- **Affected files:** None
- **Suggested fix:** None

### WARN — test-execution

Repository test execution was not requested.

- **Affected files:** None
- **Suggested fix:** Run with --run-tests before merge.
