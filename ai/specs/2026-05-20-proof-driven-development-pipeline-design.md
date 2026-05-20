# Proof-Driven Development Pipeline

**Date:** 2026-05-20
**Status:** Draft
**Author:** Vasco de Krijger + Claude

## Problem

Code generation with Claude is fast, but the surrounding quality assurance workflow has gaps:

1. **Testing coverage** — Claude skips edge cases, there's no confidence that all paths are covered, and discovering missing paths is slow/manual.
2. **Spec conformance** — requirements from the spec get partially implemented and the two-stage review (spec compliance + code quality) doesn't reliably catch all gaps.
3. **No proof trail** — even when things work, there's no artifact showing what was tested, what passed, or what the coverage looks like.
4. **No rerunnability** — after running simplify or refactors, there's no quick way to re-verify everything still satisfies the spec.

## Existing Foundation

The following tools are already in place and working well:

- **Superpowers brainstorming** — spec-driven development with design docs
- **Superpowers writing-plans + subagent-driven-dev** — plan execution with two-stage review (spec compliance + code quality)
- **Superpowers TDD skill** — red-green-refactor discipline
- **Superpowers verification-before-completion** — evidence-before-claims
- **Review-swarm skill** — parallel multi-reviewer pipeline (simplify + vasco/sre/xp/code-reviewer/qa-team) with convergence analysis, risk scoring, HTML report, and calibration feedback loops

The problem is not missing tools but gaps in how they connect — specifically around edge case discovery, spec-to-test traceability, visual proof, and rerunnability.

## Solution: Proof-Driven Development Pipeline

### Pipeline Overview

```
Phase 1: SPEC + CRITERIA
  superpowers:brainstorming → spec doc → criteria extraction (NEW) → criteria matrix

Phase 2: IMPLEMENTATION
  writing-plans → subagent-driven-dev (implementer satisfies criteria matrix)

Phase 3: VERIFICATION
  verify-and-prove (NEW) → verification report + rerunnable script + visuals

Phase 4: HUMAN CHECKPOINT
  human-checkpoint (NEW) → guided review prompt with visuals + specific instructions
  └── iterate on feedback → re-verify after each change

Phase 5: PRODUCTION HARDENING
  /review-swarm in iteration loop → fix findings → re-verify → repeat until grade ≥ A-

Phase 6: FINAL VERIFICATION + PR
  verify-and-prove (rerun) → fresh report + visuals → PR with proof artifacts

Phase 7: HUMAN FINAL REVIEW
  human reviews PR → opens for internal review
```

### Artifacts That Flow Through the Pipeline

1. **Criteria matrix** (Phase 1) — the testable contract everything is verified against
2. **Verification report** (Phase 3/6) — traceability matrix + test output + visuals
3. **Rerunnable verify script** (Phase 3) — re-executable after any change
4. **Review-swarm report** (Phase 5) — the production quality gate
5. **PR with proof** (Phase 6) — the final deliverable with visual evidence

---

## Phase 1: Enhanced Spec + Acceptance Criteria Extraction

### What Changes

Superpowers brainstorming remains the foundation — it produces the spec doc as it does today. A new step runs **after** the spec is written and approved but **before** writing the implementation plan.

### Criteria Extraction Step

A dedicated "test architect" subagent reads the spec with fresh eyes (separate from whoever wrote the spec, to catch blind spots) and produces a criteria matrix.

**Process:**

1. Read the completed spec doc
2. For each feature/requirement, extract:
   - **Requirement ID** (e.g. `REQ-01`)
   - **Description**
   - **Happy path** (expected behavior)
   - **Edge cases** (boundary conditions, empty inputs, concurrent access, error states)
   - **Proof type** — what constitutes evidence: `test`, `visual` (screenshot), `visual-flow` (GIF), or `manual` (human must check)
3. Apply a systematic edge case checklist to every requirement:
   - Null/empty/missing inputs
   - Boundary values (0, 1, max, max+1)
   - Error/failure states (network, timeout, permission)
   - Concurrent/race conditions (where applicable)
   - State transitions (what happens between states)
   - Authorization/access edge cases

### Criteria Matrix Format

Optimized for agent consumption — structured, unambiguous, machine-parseable:

```
CRITERIA_MATRIX:
  source_spec: <path to spec doc>
  generated_at: <timestamp>

REQUIREMENTS:
  - id: REQ-01
    description: <what it does>
    happy_path: <expected behavior>
    proof_type: [test, visual]
    edge_cases:
      - id: EC-01a
        description: <edge case>
        proof_type: [test]
      - id: EC-01b
        description: <edge case>
        proof_type: [test, visual]

  - id: REQ-02
    ...
```

### Integration Point

The criteria matrix is passed to the plan writer as input, so the implementation plan references specific requirement IDs. The implementer knows exactly what to satisfy.

**Output:** `docs/superpowers/specs/YYYY-MM-DD-<topic>-criteria-matrix.md` (alongside the spec doc, path follows project conventions)

---

## Phase 2: Implementation

No changes to the existing workflow. Subagent-driven development executes the plan as it does today. The key difference is that the plan now references criteria matrix IDs, so:

- The implementer knows each requirement's edge cases upfront
- The spec reviewer checks against the criteria matrix (not just the prose spec)
- TDD cycle targets specific REQ/EC items

---

## Phase 3: Verify-and-Prove

### Overview

New skill that walks the criteria matrix line by line, runs tests, captures visuals, and produces a verification report + a rerunnable script. Runs twice in the pipeline — after implementation (Phase 3) and after review-swarm hardening (Phase 6).

### Inputs

- Path to the criteria matrix
- Project test command(s)
- Whether this is a first run or re-run

### Process

1. **Parse the criteria matrix** — load all REQ/EC items
2. **For each requirement:**
   - Find the test(s) that cover it (by convention: test names reference the REQ/EC ID, or grep for the relevant function/behavior)
   - Run the test(s), capture pass/fail + output
   - If proof type includes `visual`: take a screenshot via browser tools
   - If proof type includes `visual-flow`: record a GIF of the interaction
   - If no test exists for a requirement: flag as **UNCOVERED**
3. **Edge case gap detection:** Compare criteria matrix edge cases against actual tests. Flag any edge case with no corresponding test.

### Output 1: Verification Report

Structured for agent consumption:

```
VERIFICATION_REPORT:
  spec: <path to spec>
  criteria: <path to criteria matrix>
  run_at: <timestamp>
  status: PASS | FAIL | PARTIAL

RESULTS:
  - id: REQ-01 | status: PASS | tests: 3/3 | visual: screenshots/req-01-widget-created.png
  - id: EC-01a | status: PASS | tests: 1/1
  - id: EC-01b | status: FAIL | tests: 0/1 | note: no test found for duplicate name handling
  - id: REQ-02 | status: PASS | tests: 2/2 | visual: screenshots/req-02-pagination.gif

UNCOVERED:
  - EC-01e: Submit while offline — no test exists
  - EC-03b: Concurrent widget deletion — no test exists

SUMMARY:
  total: 24 | pass: 21 | fail: 1 | uncovered: 2
  visual_artifacts: 8 screenshots, 2 gifs
```

**Location:** `docs/superpowers/verification/YYYY-MM-DD-<topic>-report.md`

### Output 2: Rerunnable Verify Script

A shell script that:
- Runs the relevant test suite
- Checks each criteria matrix item against test results
- Outputs a pass/fail summary
- Can be re-executed after simplify, refactors, or any change
- Exits non-zero if any requirement is FAIL or UNCOVERED

**Location:** `scripts/verify-<topic>.sh`

### Output 3: Visual Artifacts

Screenshots (PNG) and GIFs stored alongside the report, referenced by requirement ID.

**Location:** `docs/superpowers/verification/screenshots/`

### Re-run Behavior

When invoked a second time (Phase 6, after review-swarm), it re-runs the same checks using the existing verify script. Visuals are recaptured fresh since code may have changed during hardening.

### Non-UI Projects

For projects without a browser/UI (pure backend, CLI tools, libraries):
- Proof types `visual` and `visual-flow` are skipped gracefully — the criteria matrix simply won't include them
- The criteria extraction step only assigns visual proof types when the spec describes user-facing UI
- The verify script and verification report work identically — they just won't have visual artifact sections

### Boundary

Verify-and-prove does NOT fix anything. If requirements are uncovered or failing, it reports that — the implementation loop or the human decides what to do.

---

## Phase 4: Human Checkpoint

### Overview

After verify-and-prove, Claude presents a structured prompt guiding the human on exactly what to focus on.

### Prompt Contents

1. **What changed** — high-level summary of what was implemented (from the plan/spec, not a code diff dump)
2. **Verification status** — the verification report summary (X/Y requirements passing, N uncovered)
3. **Visual evidence** — embedded or linked screenshots/GIFs of the key flows
4. **What to check** — prioritized list of things needing human judgment:
   - Anything marked `manual` proof type in the criteria matrix
   - UX/feel aspects automated tests can't judge (does this feel right, is the wording good, does the layout make sense)
   - Any UNCOVERED items from the verification report that need a human decision (add a test, or acceptable risk?)
5. **How to check** — specific instructions: which URL to visit, what to click, what to look for. Not "check the feature works" but "open /settings, click Create Widget, enter Test Widget, submit — you should see it appear in the list below"

### Design Principle

The human should NOT re-check what tests already verified. The checkpoint focuses exclusively on things machines can't evaluate — UX feel, copy/wording, business logic nuance, and risk acceptance decisions.

### Iteration Loop (Step 4a)

If the human has feedback:
1. Claude captures the feedback as concrete changes
2. Makes the changes
3. Re-runs verify-and-prove (using the rerunnable script for speed)
4. Presents a new checkpoint showing only what changed since last review
5. Repeats until the human approves

---

## Phase 5: Review-Swarm Hardening Loop

### Overview

Uses the existing review-swarm skill wrapped in an automated iteration loop targeting grade A-.

### Flow

```
Run /review-swarm --no-gate
       │
  Grade ≥ A-? ──yes──▶ Continue to Phase 6
       │
       no
       │
  Claude fixes all findings (CRITICAL → HIGH → MEDIUM → LOW)
       │
  Re-run verify script (catch regressions from fixes)
       │
  Re-run /review-swarm
       │
  (repeat)
```

### Key Behaviors

- **`--no-gate`** on re-runs since Claude is driving the loop, not a human
- **Fix priority order:** CRITICAL → HIGH → MEDIUM → LOW. NITs are optional — stop at A- rather than chasing perfection
- **Regression guard:** After each fix pass, re-run the verify script before re-running review-swarm. If verify fails, fix the regression first.
- **Pass cap:** Honor the review-swarm's existing 2-pass soft cap. After 2 full passes with grade still below A-, escalate to the human with: current grade, remaining findings, and a recommendation (fix manually vs. accept the grade)
- **Diminishing returns awareness:** Review-swarm's built-in pass-cap warns about defense-amplification risk on pass 3+. The loop respects that.

### No Changes to Review-Swarm

Review-swarm itself is unchanged. The iteration loop wraps it from the outside. Review-swarm stays local-only, read-only git, same as today.

---

## Phase 6: Final Verification + PR Creation

### Step 1: Final Verification

Re-run verify-and-prove one last time — the "seal" confirming nothing broke during hardening.

- Recaptures all visuals fresh (code may have changed during hardening)
- If any requirement is FAIL or UNCOVERED: escalate to the human, don't create the PR with known gaps

### Step 2: Assemble Proof Artifacts

Collect into a proof directory (project-configurable):
- Final verification report
- Screenshots (PNGs for static states)
- GIFs (for interaction flows)
- Test output summary
- The criteria matrix (shows what was verified against)

### Step 3: Create PR

Use `gh pr create` with the **repo's PR template** (`.github/PULL_REQUEST_TEMPLATE.md` or equivalent). Fill in every section properly, then enhance with:

- **Visual proof** embedded in the PR body (GitHub renders images/GIFs inline)
- **Verification summary** — criteria pass count, review-swarm grade, link to verification report in the branch
- **Verify script reference** — `./scripts/verify-<topic>.sh` so any reviewer can independently verify
- **"How to Review" guidance** — separates what tests already prove from what needs human judgment

---

## Phase 7: Human Final Review

The human reviews the PR, optionally runs the verify script for independent confirmation, and opens it for internal review when satisfied. The proof artifacts make this review faster because the evidence is already assembled.

---

## Design Principles

### Acceptance Test Driven Development (ATDD)

The criteria matrix is extracted before implementation begins. The implementer codes against testable acceptance criteria, not just a prose spec. Edge cases are discovered at design time, not found (or missed) after the fact.

### Full Traceability

Every requirement traces through the pipeline:
```
Spec requirement → Criteria matrix ID → Test(s) → Verification report → PR proof
```
At any point you can ask "is REQ-03 satisfied?" and get a definitive answer with evidence.

### Shift-Left Edge Case Discovery

The test architect subagent applies a systematic checklist to every requirement. This catches edge cases that typically get skipped — not because the implementer is careless, but because they weren't systematically prompted to think adversarially about each requirement.

### Separation of Concerns in Verification

Automated checks prove what machines can prove. Human checkpoints focus exclusively on what needs human judgment. Nobody wastes time re-checking what the other already verified.

### Regression Safety by Default

The rerunnable verify script means any change — simplify, refactor, review-swarm fix — can be immediately checked against the full criteria matrix. This makes the iteration loops (Phase 4a and Phase 5) safe.

### Graceful Escalation, Not Infinite Loops

Both the human checkpoint loop and the review-swarm loop have escape hatches. If criteria can't be fully satisfied or grade can't reach A-, the pipeline escalates to the human with clear context rather than spinning.

---

## New Components to Build

| Component | Type | Description |
|-----------|------|-------------|
| Criteria extraction | Skill or step within brainstorming flow | Extracts testable criteria matrix from approved spec |
| Verify-and-prove | Skill | Walks criteria matrix, runs tests, captures visuals, generates report + rerunnable script |
| Human checkpoint | Skill or structured prompt template | Guides human on what to check with specific instructions and visuals |
| Review-swarm iteration wrapper | Enhancement to workflow | Wraps review-swarm in fix-and-rerun loop targeting A- |
| PR proof assembly | Step within PR creation flow | Collects proof artifacts and enhances repo PR template |

## Dependencies

- Superpowers plugin (brainstorming, writing-plans, subagent-driven-dev, TDD, verification-before-completion)
- Review-swarm skill
- Browser tools (Claude in Chrome or equivalent) for screenshot/GIF capture
- `gh` CLI for PR creation
