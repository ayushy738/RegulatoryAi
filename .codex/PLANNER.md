
# RegulatoryAI Planner

Version: 1.0

This document defines how Codex chooses work before writing code.

---

# Objective

Never begin implementation without first producing a deterministic plan.

Planning always precedes coding.

The planner never edits code.

The planner only decides:

- what should be built
- why
- dependencies
- risks
- expected files
- completion criteria

---

# Planning Sequence

Read in order:

1. .codex/AGENTS.md
2. docs/ASK_AI/00_MASTER_LOOP.md
3. docs/ASK_AI/04_CURRENT_STATE.md
4. docs/ASK_AI/08_BLOCKERS.md
5. docs/ASK_AI/03_TASKS.md

Then inspect

- git status
- current branch
- repository structure

---

# Task Selection Rules

Choose exactly ONE task satisfying:

✓ Highest Priority

✓ Dependencies Complete

✓ Not Blocked

✓ Not Already Active

✓ Compatible with current repository state

If CURRENT_STATE already specifies an active task,

continue it.

Never select another task.

---

# Before Coding

Produce an internal execution plan.

The plan should include

## Task

Current task identifier.

Example

E0.1

---

## Goal

What success looks like.

---

## Scope

Exactly what is allowed.

Exactly what is out of scope.

---

## Files Expected

List probable files that should change.

Avoid touching unrelated files.

---

## Tests Required

Determine:

Unit

Integration

Contract

Regression

Typecheck

Build

---

## Risks

Possible failures.

Migration risk

Breaking API

Authentication

Data loss

Performance

Concurrency

Compatibility

---

## Definition of Done

Copy task-specific completion criteria.

---

# Scope Protection

Never expand scope.

If another issue is discovered

record it.

Do not fix it unless:

- it blocks current task
- it is a critical security issue
- it causes test failure

Otherwise continue.

---

# Planning Constraints

Never

- redesign architecture
- invent requirements
- modify frozen specifications
- skip dependencies
- perform unrelated cleanup

---

# Output Contract

Every plan should answer

1. What task am I implementing?
2. Why now?
3. Which files will likely change?
4. Which tests will prove completion?
5. What documents require updates?

Only after these questions are answered may implementation begin.

---

# Handoff

When planning completes

handoff to Builder.

Builder follows AGENTS.md.

Planner does not write code.
