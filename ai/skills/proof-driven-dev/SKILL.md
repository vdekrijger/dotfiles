---
name: proof-driven-dev
description: Use when starting any feature, fix, or change that should ship with proof of work — spec-to-PR traceability via the brainstorming pipeline, criteria matrix, and verification. Full mode for features, lightweight mode for quick fixes.
---

# Proof-Driven Development

Build from idea to merge-ready PR with full proof of work: every requirement traced from spec → criteria → tests → verification report → PR.

## Mode Selection

Pick the right mode — the full pipeline on a 5-line bugfix wastes time; lightweight mode on a complex feature misses edge cases. When in doubt, **ask the human** — don't guess on ambiguous cases.

| Signal | Mode |
|---|---|
| New feature or significant behavior change | full |
| Touches 5+ files or 3+ modules | full |
| Has UI that needs visual proof | full |
| User explicitly requests full pipeline | full |
| Bugfix with clear scope (1-3 files) | lightweight |
| Config change, copy change, dependency bump | lightweight |
| Refactor with existing test coverage | lightweight |
| Estimated implementation < 30 min | lightweight |

### Lightweight Mode

1. Implement the fix (TDD — write failing test first)
2. Run all tests
3. Run `/review-swarm --no-gate` (single pass, no iteration loop)
4. Fix any CRITICAL or HIGH findings
5. Create PR (repo template, no proof artifacts)
6. Monitor CI + bot comments
7. Human final review

Skips: brainstorming, criteria extraction, formal verification report, human checkpoint, review-swarm iteration loop, visual proof capture. Still uses TDD, still runs review-swarm once, still monitors CI.

**Upgrading mid-flight:** if scope grows or edge cases multiply, stop and say so. The human can upgrade to full mode — go back and write a spec + criteria matrix for the expanded scope.

## Full Mode Pipeline

Phases in order, with gates:

1. Brainstorm + spec
2. Extract criteria
3. Write plan
4. Implement
5. Verify + prove
6. Human checkpoint — gate: human approves; if not, fix + re-verify, repeat phase 6
7. Review-swarm loop — gate: grade ≥ A-; if not, fix findings + re-verify and rerun; after 2 passes still below A-, escalate to human (escalation goes straight to phase 11)
8. Final verify
9. Create PR with proof
10. CI monitor — gate: CI green + bot comments addressed; auto-fix and re-poll, ask human when input is needed
11. Human final review
12. Maintenance feedback loop (after merge)

## Phase 1: Brainstorm + Spec

**Invoke:** `brainstorming` skill. (In Hermes, Superpowers skills installed from `obra/superpowers` are exposed by unqualified names via `skills.external_dirs` — e.g. `brainstorming`, not `superpowers:brainstorming`.)

Follow the full flow: explore context, ask clarifying questions one at a time, propose approaches, present design, write spec.

**Inverse pass (mandatory):** after proposing 2-3 approaches, before settling on one, ask: "What's the strongest argument against each approach? What assumptions are we making that could be wrong?" Do this even when the recommendation seems obvious — cheap approaches hide the most expensive surprises.

## Phase 2: Extract Criteria

**Invoke:** `criteria-extraction` skill — produces the testable contract for the rest of the pipeline. Review the matrix; if any requirement is under-specified on edge cases, re-dispatch the test architect with guidance on what to probe.

**Challenge-criteria pass (mandatory):** after the matrix is produced, run one inverse pass against the spec itself: "What assumptions does this spec make that could be wrong? What edge cases are we implicitly ignoring? What would break if the most optimistic assumption turned out false?" Record resulting testable assertions as `CHALLENGE` items in the matrix — not implementation requirements unless the human promotes them.

**Proportionality gate:** the criteria-extraction skill enforces edge-case ceilings by feature complexity and lets the human triage **must-have** vs **nice-to-have**. Enforce the outcome: must-have cases are the implementation contract; nice-to-have cases are tracked but never block verification (`OPTIONAL` in the report, not `UNCOVERED`).

## Phase 3: Write Plan

**Invoke:** `writing-plans` skill. The plan must reference criteria matrix IDs — each task states which REQ/EC items it satisfies.

## Phase 4: Implement

**Invoke:** `subagent-driven-development` skill. Execute the plan task-by-task; provide the criteria matrix to the spec reviewer so it checks testable criteria, not just prose. Create a feature branch before starting — never commit to main/master.

## Phase 5: Verify + Prove

**Invoke:** `verify-and-prove` skill with mode `full`. Produces: verification report (traceability matrix, pass/fail per requirement), rerunnable verify script, visual artifacts (screenshots/GIFs).

**Adversarial verification pass (mandatory):** after all tests pass, ask: "If this feature were broken despite all tests passing, where would the bug hide? What test gap would it exploit? What production-only condition would trigger it?" (Surfaces missing integration tests, race conditions, timeout/retry interactions, data-dependent edge cases, config/environment assumptions.) Record identified gaps as `ADVERSARIAL` items in the verification report; fix the testable ones, escalate the ones that need production monitoring.

If the report shows FAIL or UNCOVERED items: debug FAILs, write missing tests for UNCOVERED, re-run verify-and-prove in `rerun` mode, repeat until PASS.

## Phase 6: Human Checkpoint

Present a guided review prompt using `references/human-checkpoint-template.md`, all placeholders filled from the verification report.

The human should NOT re-check what tests already verified. Focus them on: proof type `manual` items; UX feel, copy quality, layout; UNCOVERED items needing a risk-acceptance decision; specific check instructions (URLs, clicks, expected results).

On feedback: capture it as concrete changes, make them, re-run verify-and-prove in `rerun` mode, present a fresh checkpoint showing only what changed. Repeat until approved.

## Phase 7: Review-Swarm Hardening Loop

Target grade A-:

1. Run `/review-swarm --no-gate`, parse the grade
2. Grade ≥ A-: exit loop, continue to Phase 8
3. Grade < A-: fix findings in order CRITICAL > HIGH > MEDIUM > LOW, re-run the verify script (if it fails, fix the regression first), commit, go to step 1

**Change-size circuit breaker:** before applying any fix, if it touches more files than the finding references, OR adds more lines than the finding complained about, OR introduces a new abstraction (helper, wrapper, utility) that didn't exist before — STOP and surface it before applying (prevents the "fix a nit by adding an abstraction layer" trap):

```
[proof-driven-dev] Review-swarm fix seems disproportionate:

  Finding: {FINDING_SUMMARY} (severity: {SEVERITY})
  Proposed fix: {FIX_SUMMARY}
  Fix scope: {N files, M lines added}

  This fix is larger than the issue it addresses. Apply it, skip it,
  or simplify?
```

**Pass cap:** after 2 full passes with grade still below A-, escalate:

```
[proof-driven-dev] Review-swarm has run 2 passes. Current grade: {GRADE}
  Remaining findings:
  {FINDING_LIST}

  Options:
  1. Continue with another pass (diminishing returns likely)
  2. Accept current grade and proceed to PR
  3. Fix remaining issues manually

  What would you like to do?
```

## Phase 8: Final Verification

Re-run verify-and-prove in `rerun` mode — the "seal" confirming hardening broke nothing. Recapture all visuals fresh. Any FAIL: escalate to the human, don't create the PR.

## Phase 9: Create PR with Proof

1. Collect proof artifacts into the branch (verification report, screenshots, GIFs, criteria matrix)
2. Read the repo's PR template (`.github/PULL_REQUEST_TEMPLATE.md` or equivalent) and fill every section faithfully
3. Enhance with proof sections using `references/pr-proof-template.md`
4. Create the PR via `gh pr create`

## Phase 10: CI Monitor + Bot Comments

Monitor CI and address bot comments before handing off to the human. Follow `references/ci-monitoring.md` for the full loop: polling, failure classification (auto-fixable vs needs-human-input), bot comment triage, and the escalation prompt.

**Safety rules:**
- Re-run the verify script after every CI fix push to catch regressions
- Never force-push to fix CI — always add new commits
- After 3 fix-push cycles on the same check, escalate to the human rather than looping (the fix might be making things worse)
- Never dismiss or resolve bot comments without addressing them

## Phase 11: Human Final Review

Present the PR link with CI status. The human reviews, optionally runs `./scripts/verify-<topic>.sh` for independent confirmation, and opens for internal review when satisfied.

## Phase 12: Maintenance — Feedback Loop (after PR lands)

After merge, when human review feedback arrives:

1. **Single-PR mining:** `pr-feedback-miner --local --pr <merged-number>` — classifies every human correction, generates WIN entries for review-swarm calibration
2. **Periodic bulk mining:** weekly or after a batch of PRs: `pr-feedback-miner --local --since last-week --auto-apply` — finds recurring patterns, proposes vasco-reviewer priority updates
3. **Apply calibration:** review the miner's report; apply WIN entries to `review-swarm/references/wins.md` and proposed updates to `vasco-reviewer/SKILL.md`. The next review-swarm run picks them up automatically.

Every correction the human makes once should never need to be made again.

## Pro Prompting Techniques

The mandatory adversarial passes are baked into phases 1 (inverse questioning), 2 (challenge criteria), and 5 (adversarial verification). For ad-hoc techniques when a decision, design, or implementation needs stress-testing — pre-mortem, steel-man alternatives, constraint relaxation, confidence calibration, recursive decomposition, rubber-duck inversion — see `references/prompting-techniques.md`.

## Rules

- **Never skip criteria extraction.** Without it, verification has nothing to verify against.
- **Never skip verification.** The formal report + script are the proof of work, even if all tests passed during implementation.
- **Never create the PR with known failures.** If verify-and-prove reports FAIL, fix it or escalate.
- **Never skip the human checkpoint.** The human must see the feature and approve before hardening begins.
- **Never loop forever.** Both the human checkpoint and review-swarm loops have escape hatches — use them.
- **Repo template first.** The PR uses the repo's own template, enhanced with proof — not a custom format.
- **Verify script is permanent.** Committed to the repo, re-runnable by anyone at any time — the durable proof artifact.
