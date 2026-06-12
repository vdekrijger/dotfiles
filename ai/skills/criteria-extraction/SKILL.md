---
name: criteria-extraction
description: Use when a spec has been approved via superpowers:brainstorming and a testable criteria matrix (requirements, edge cases, proof types) is needed before superpowers:writing-plans — the contract the proof-driven pipeline verifies against.
---

# Criteria Extraction

Read an approved spec and produce a machine-parseable criteria matrix — the testable contract that implementation, verification, and review all verify against. Runs after the spec is approved, before the implementation plan.

## Process

Read spec → read edge-case checklist → dispatch test architect subagent → review matrix (re-dispatch on gaps) → proportionality check → write to disk → commit → report.

### Step 1: Read inputs

1. The approved spec (path from caller, or the project's spec directory)
2. `references/edge-case-checklist.md`

### Step 2: Dispatch test architect

Dispatch a subagent with the prompt template at `references/test-architect-prompt.md`, providing the full spec content, full edge-case checklist content, and spec file path (for the `source_spec` output field). Use `model: "opus"` — this needs adversarial thoroughness, not speed.

### Step 3: Review the matrix

Check:
- Every spec section/feature has at least one REQ entry
- Every REQ has at least one edge case
- Edge case descriptions are specific, not vague
- SUMMARY counts match actual entries
- No `visual`/`visual-flow` proof types on non-UI features

If gaps exist, re-dispatch the subagent with specific instructions on what was missed.

### Step 4: Proportionality check

Sanity-check edge case count against feature complexity before writing:

| Feature complexity | Expected edge cases per REQ | Total ceiling |
|---|---|---|
| Simple (CRUD, config, single form) | 3-5 | ~20 |
| Medium (multi-step flow, integrations) | 5-10 | ~50 |
| Complex (real-time, concurrent, multi-system) | 10-15 | ~80 |

If the matrix significantly exceeds the ceiling:

1. Present to the human:
   ```
   [criteria-extraction] Matrix has {N} edge cases for {M} requirements.
     This seems high for a {COMPLEXITY} feature (ceiling: ~{CEILING}).
     Would you like to triage edge cases into must-have vs nice-to-have?
   ```
2. If yes: present edge cases grouped by requirement; the human marks each `must-have` or `nice-to-have`
3. Add a `priority` field per edge case: `must-have` blocks verification (UNCOVERED if untested); `nice-to-have` is tracked but non-blocking (OPTIONAL)
4. If the human accepts all: every edge case is `must-have`

### Step 5: Write and commit

Write to the spec's directory: `<spec-dir>/YYYY-MM-DD-<topic>-criteria-matrix.md`. Commit: `Add criteria matrix for <topic>`.

### Step 6: Report to caller

```
[criteria-extraction] Matrix written to <path>
  Requirements: N
  Edge cases: N (M must-have, K nice-to-have)
  Proof types: N test-only, N visual, N visual-flow, N manual
```

## Rules

- **Never invent requirements.** The matrix tests what the spec says; scope expansion belongs in the spec, not here.
- **Never skip the edge case checklist.** Evaluate every category against every requirement. Over-generation is acceptable; under-generation is not.
- **Proportionality matters.** The human must get the chance to triage before implementation — 60 edge cases on a simple feature wastes time.
- **Fresh eyes only.** The test architect subagent gets NO conversation history; it reads the spec cold, like an external QA engineer.
- **One matrix per spec.** Multiple independent subsystems should have been split during brainstorming — if not, flag it and suggest splitting.
