---
name: review-swarm-v2
description: Use when invoked as /review-swarm-v2, or when the user wants a review pass that also applies the fixes and proves them green before pushing. Hardened harness around review-swarm — worktree isolation, measured baselines, verified postflight gate, signed commits.
---

# Review swarm v2

`review-swarm` finds problems and refuses to touch git. `polish-pr` applies and pushes. Neither
proves that what it applied is actually green, in the right directory, on top of a baseline that
separates pre-existing failures from newly introduced ones. That gap is what this skill closes.

It does not reimplement the reviewers. The six calibrated personas, their false-positive and wins
calibration, the convergence analysis and the HTML report all come from `review-swarm`, which stays
the single source of review logic. v2 wraps it in a harness.

```
Stage A  preflight   → validate args, build worktree, measure baseline   → GATE
Stage B  review      → delegate to review-swarm, pinned to the worktree
Stage C  apply       → fix findings in the worktree
Stage D  postflight  → re-run gates, diff vs baseline, check callers     → GATE
Stage E  land        → signed commits, verified, hand back the push
```

**Hard rules:**

- **Every path is absolute.** Never let a subagent or a Bash call inherit cwd. Every subagent prompt
  carries `$WT` and starts by verifying it.
- **A gate that is not green does not pass.** Never report success from a claim. Paste the command
  output, or say it did not run.
- **A failure is only yours if the baseline was green.** Stage A exists so this is measured, not argued.
- **Signed commits only** (`git commit -S`). Never `--rebase-merges`. Never force-push without asking.
- **Stop at the push.** Opening the PR is fine; pushing to a shared branch and merging are the user's.

## Invocation

```
/review-swarm-v2 [<branch>] [--repo <path>] [--baseline full|fast|skip] [--gate "<cmd>"]... [--no-apply]
```

Defaults: `<branch>` is the current branch of `--repo`, which defaults to the cwd's repo root.
`--baseline full` runs the repo's whole gate set, `fast` runs only gates reachable from the diff,
`skip` records no baseline and forfeits the pre-existing-versus-introduced distinction.

## Stage A: preflight

Run `scripts/preflight.sh`. It fails fast and prints a JSON summary to `$WT/.rsv2/preflight.json`.

```bash
"$SKILL_DIR/scripts/preflight.sh" --repo "$REPO" --branch "$BRANCH" --baseline "$BASELINE"
```

It does six things, in order, and stops at the first that fails:

1. **Arg validation.** Every templated value is non-empty and resolves. An empty `--branch` or a
   `--repo` that is not a git repo fails here with the name of the offending argument, rather than
   reaching a subagent as the literal string `undefined`.
2. **Worktree.** Creates a detached worktree at an explicit absolute path and echoes it. Detached,
   because the branch is checked out in the user's main tree and git will not check it out twice.
3. **Self-check.** Asserts `git -C "$WT" rev-parse --show-toplevel` equals `$WT`.
4. **Rebase status.** Reports how far behind `origin/<default>` the branch is. Being behind is a
   warning, not a failure — but flaky Playwright and snapshot failures usually mean stale, so try a
   merge before believing any red gate.
5. **Interpreter sanity.** Checks the resolved Python against the repo's `requires-python`, because a
   stale venv reads modern type annotations as syntax errors and produces a fake wall of mypy errors.
6. **Baseline.** Runs the gates and records each one's exit code and failing-test count.

**GATE.** Show the user the worktree path, the rebase distance and the baseline result. If the
baseline is already red, say which gates and how badly, and ask whether to continue. A red baseline
is not a blocker, it is a measurement — but reviewing on top of one without saying so is how a
pre-existing failure gets attributed to this branch.

## Stage B: review

Invoke the `review-swarm` skill with `--sha` pinned to the worktree's range, and prefix its
invocation context with:

```
All file reads and commands for this review run in the worktree $WT.
Before your first Read or Bash call, run: pwd && git rev-parse --show-toplevel
Abort loudly if it is not $WT. Do not use any other checkout of this repo.
```

Two additions to what v1 already asks its reviewers:

- **Simplicity bias.** Tell the xp reviewer explicitly to flag hand-rolled engines, policy layers and
  filters that duplicate something the framework or repo already ships, and to prefer reuse over a new
  abstraction. It should name the existing component as `file:symbol`. Also flag comments that restate
  the code for deletion.
- **Verification bias.** No finding asserts that an API, flag or option is unsupported, or that a bug
  is pre-existing, without two independent checks — a source read and runtime or test evidence — cited
  in the finding. Otherwise it is `confidence: speculative`.

v1 owns everything else: dispatch, schema, convergence, calibration, grading, the report.

## Stage C: apply

Skip entirely under `--no-apply` and hand back the report.

Apply the findings the user accepts, in the worktree, severity first. Two rules:

- Do not widen the diff. A finding is a fix, not an invitation to refactor around it.
- Record every function whose signature you changed. Stage D needs the list.

## Stage D: postflight

Run `scripts/postflight.sh`. It re-runs the same gates in the worktree and compares against the
baseline, so its verdict is per-gate: green, still-red-from-baseline, or newly red.

```bash
"$SKILL_DIR/scripts/postflight.sh" --worktree "$WT" --baseline "$WT/.rsv2/preflight.json"
```

It also does the check that catches the fix which broke something else: for every function whose
signature changed, grep the repo for its callers and list any whose argument count no longer matches.
This is a heuristic, not a type checker — it surfaces candidates for you to read, and the typecheck
gate is what actually proves it.

**GATE.** Newly red gates block. Report which gate, which tests, and the output. Fix and re-run.
Never proceed to Stage E on a claim that something passes.

## Stage E: land

1. Commit in review-order — one logical change per commit, mechanical fallout separate.
2. `git commit -S`. If a rebase drops signatures, re-sign the range with
   `git rebase --exec 'git commit --amend --no-edit -S' <base>`. Never `--rebase-merges`.
3. Verify before pushing: `git log --show-signature -1` must show a good signature.
4. Push. If the push needs a Touch ID prompt and the user is away, hand back the exact command
   instead of trying to route around the key.
5. Copy the commits back to the user's main checkout only if they ask. Otherwise leave the worktree
   in place and tell them where it is — `git worktree remove "$WT"` when they are done.

## Cleanup

The worktree is deliberately not removed automatically. It holds the applied fixes and the gate
output, which is the evidence for the handback. Print the removal command; let the user run it.

## Graceful degradation

- `review-swarm` not installed → say so and stop. v2 has no reviewers of its own by design.
- No `origin/master` → skip the rebase check with a note, continue.
- A gate command not found in this repo → record `skipped (not present)`, never a pass.
- `--baseline skip` → Stage D reports raw pass/fail and says the pre-existing distinction is unavailable.
- Worktree creation fails (dirty index, locked ref) → stop. Never fall back to reviewing in the user's
  main checkout, which is how a stash once ate local-only changes.
