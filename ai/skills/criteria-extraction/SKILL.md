---
name: criteria-extraction
description: Extract a testable criteria matrix from an approved spec. Use after superpowers:brainstorming writes the spec and before superpowers:writing-plans. Produces a structured matrix of requirements, edge cases, and proof types that the rest of the proof-driven pipeline verifies against.
---

# Criteria Extraction

Read an approved spec and produce a machine-parseable criteria matrix —
the testable contract that the implementation, verification, and review
phases all verify against.

## When to Use

After the spec is written and approved (via superpowers:brainstorming),
before writing the implementation plan. This is the bridge between
"what we're building" and "how we know it's built correctly."

## Process

```dot
digraph criteria_extraction {
    "Read approved spec" [shape=box];
    "Read edge case checklist" [shape=box];
    "Dispatch test architect subagent" [shape=box];
    "Subagent produces criteria matrix" [shape=box];
    "Review matrix for completeness" [shape=diamond];
    "Write matrix to disk" [shape=box];
    "Commit" [shape=doublecircle];

    "Read approved spec" -> "Read edge case checklist";
    "Read edge case checklist" -> "Dispatch test architect subagent";
    "Dispatch test architect subagent" -> "Subagent produces criteria matrix";
    "Subagent produces criteria matrix" -> "Review matrix for completeness";
    "Review matrix for completeness" -> "Dispatch test architect subagent" [label="gaps found"];
    "Review matrix for completeness" -> "Write matrix to disk" [label="complete"];
    "Write matrix to disk" -> "Commit";
}
```

### Step 1: Read inputs

1. Read the approved spec doc (path provided by caller or found in
   the project's spec directory)
2. Read `references/edge-case-checklist.md`

### Step 2: Dispatch test architect

Dispatch a subagent using the prompt template at
`references/test-architect-prompt.md`. Provide:
- The full spec content
- The full edge case checklist content
- The spec file path (for the `source_spec` field in output)

Use `model: "opus"` — criteria extraction requires adversarial thinking
and thoroughness, not speed.

### Step 3: Review the matrix

After the subagent returns, check:
- Every section/feature in the spec has at least one REQ entry
- Every REQ has at least one edge case
- Edge case descriptions are specific (not vague)
- SUMMARY counts match actual entries
- No proof types reference `visual` or `visual-flow` for non-UI features

If gaps exist, re-dispatch the subagent with specific instructions about
what was missed.

### Step 4: Proportionality check

Before writing, sanity-check the edge case count against feature
complexity:

| Feature complexity | Expected edge cases per REQ | Total ceiling |
|---|---|---|
| Simple (CRUD, config, single form) | 3-5 | ~20 |
| Medium (multi-step flow, integrations) | 5-10 | ~50 |
| Complex (real-time, concurrent, multi-system) | 10-15 | ~80 |

If the matrix significantly exceeds the ceiling:

1. Present the summary to the human:
   ```
   [criteria-extraction] Matrix has {N} edge cases for {M} requirements.
     This seems high for a {COMPLEXITY} feature (ceiling: ~{CEILING}).
     Would you like to triage edge cases into must-have vs nice-to-have?
   ```
2. If the human says yes: present edge cases grouped by requirement.
   The human marks each as `must-have` or `nice-to-have`.
3. Add a `priority` field to each edge case in the matrix:
   - `must-have` — blocks verification (shows as UNCOVERED if no test)
   - `nice-to-have` — tracked but non-blocking (shows as OPTIONAL)
4. If the human says no (accepts all): proceed with all edge cases as
   `must-have`.

### Step 5: Write and commit

Write the criteria matrix to the same directory as the spec:
`<spec-dir>/YYYY-MM-DD-<topic>-criteria-matrix.md`

Commit with message: `Add criteria matrix for <topic>`

### Step 6: Report to caller

Print the summary:
```
[criteria-extraction] Matrix written to <path>
  Requirements: N
  Edge cases: N (M must-have, K nice-to-have)
  Proof types: N test-only, N visual, N visual-flow, N manual
```

## Rules

- **Never invent requirements.** The matrix tests what the spec says.
  Scope expansion belongs in the spec, not here.
- **Never skip the edge case checklist.** Every category must be
  evaluated against every requirement. Over-generation is acceptable;
  under-generation is not.
- **Proportionality matters.** Over-generation is acceptable at the
  extraction stage, but the human must have the chance to triage before
  implementation. A simple feature buried under 60 edge cases wastes
  implementation time.
- **Fresh eyes only.** The test architect subagent must NOT receive
  the conversation history. It reads the spec cold, like an external
  QA engineer.
- **One matrix per spec.** If the spec covers multiple independent
  subsystems, it should have been split during brainstorming. If it
  wasn't, flag this and suggest splitting.
