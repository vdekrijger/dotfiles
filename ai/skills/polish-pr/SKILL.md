---
name: polish-pr
user_invocable: true
disable-model-invocation: true
description: Use when invoked as /polish-pr <pr-number-or-url>, or asked to take an open PR through local review iterations until its grade meets a target. Local-only reviewing — findings never go to GitHub; the PR only ever receives code pushes and surgical description fixes.
---

# Polish PR

Iterate an open PR through `/review-swarm` until it grades at or above the target, push the verified fixes, and confirm e2e coverage. Ceiling: pushed fixes + a handback — never merge.

**REQUIRED SUB-SKILL:** review-swarm (the grading engine). Triage per superpowers:receiving-code-review — findings are hypotheses to verify, not verdicts to implement.

## Invocation

```
/polish-pr <pr-number-or-url> [--target=A-] [--base=<ref>] [--no-push]
```

## Target semantics

The overall scale has no minus grades (A/B/C/F). Target `A-` (default) means: **overall A** (nothing above LOW after adjustment) **and every per-reviewer grade ≥ A-**. NITs and findings the reviewer itself marks non-blocking never gate. Hitting the target ends the loop — iterating past it to chase zero findings is defense amplification, not quality.

## Pipeline

**0. Sync, don't churn.** `gh pr view <n> --json headRefName,headRefOid,state,title,body,files`. Already on the branch with HEAD == headRefOid → proceed. Behind → `git pull --ff-only`. Diverged → stop and ask. Unrelated dirty files in the tree are fine — branch-diff review never sees them; work around them (explicit-path staging only, per CLAUDE.md; never stash them out of the way).

**1. Baseline.** Run review-swarm (branch-diff vs the PR's base). Record overall + per-reviewer grades and every finding.

**2. Triage — verify before touching anything.** For each MEDIUM+ finding, check its premise against the actual code (grep the props, callers, and strings it names). Three legitimate resolutions:

- **Fix** — the premise holds. Change only files in the PR's blast radius; prove the fix with the affected test (run it; 3× when timing-sensitive).
- **Document** — the flagged behavior is intentional (e.g. a deliberate UX overlap). Add the one-line why at the site; reviewers treat documented decisions as weighed trade-offs, not smells.
- **Reject with evidence** — the premise is false. Keep the code, cite the disproving file:line in the handback. Never implement a fix you have disproven just to move the grade.

A stated-but-not-done finding about the **PR description** is fixed on the description, not the code: re-fetch the body, splice the one stale claim, write back, verify it applied (anchor-splice per CLAUDE.md; wholesale rewrites are banned).

**3. Commit per pass** (conventional commits, explicit paths) — branch-diff mode only sees commits.

**4. Confirm cheaply.** Re-run only the reviewers whose findings you addressed (`--only <r> ...`) and carry the others' verdicts forward **when the fixes changed no behavior they graded** (comment-, test-, or description-only edits). Any fix that changed component or logic behavior → full-roster re-run. Never use `--only`/`--skip` to hide a reviewer from the grade; state carried-forward verdicts as such in the handback.

**5. Loop 2–4 until the target.** Stalls: the same finding survives two genuine fix attempts, or the fix needs a product decision or an out-of-scope surface → stop, push what's green, hand back the surviving findings verbatim with grades. Respect review-swarm's pass-cap warning (3+ passes = diminishing returns).

**6. Gates, then one push.** Changed-area gates per repo CLAUDE.md + grep-before-push. Batch all pass-commits into a single fast-forward push (`--no-push` → stop before pushing and report). If a repo-wide gate fails on surfaces the PR doesn't touch (e.g. stale kea typegen flooding tsgo), scope the signal: prove the PR's files are clean, note the environmental failure, rely on CI for the authoritative run.

**7. E2E (auto-detect).**

- A spec covering the PR's surface exists (committed or untracked-local) → verify it without requiring the full stack: compile/list it (Playwright: `--list`; bump `NODE_OPTIONS=--max-old-space-size=8192` if the collector OOMs) and cross-check every hard assertion (copy strings, data-attrs, routes) against source. Run it for real only if the stack is already up.
- The spec is **untracked** → it is not part of the PR. Ask the user: commit it to the PR, keep it local (the default when they're unreachable), or extend it first.
- No spec exists → say so and offer to write one; never block the grade loop on it.
- Hand over the exact run command + which verification level actually ran (evidence before claims).

**8. Handback.** Grade table (baseline → final, per reviewer), per-finding resolution (fixed / documented / rejected + evidence), gates run, e2e verification level + run command, asked/built/deviated delta.

## Red flags — you're drifting

- Committing an untracked file into the PR without asking
- Implementing a reviewer's fix you haven't verified — or have disproven
- A full-roster re-run to confirm a comment-only change
- A fourth pass chasing NITs after the target is met
- `git stash`, `git add -A`, or a wholesale PR-body rewrite "to be quick"
