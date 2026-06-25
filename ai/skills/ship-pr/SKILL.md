---
name: ship-pr
user_invocable: true
disable-model-invocation: true
description: Use when invoked as /ship-pr or asked to take the current branch all the way to a review-ready draft PR and drive CI to green. Never merges — stops at a draft PR for human review.
---

# Ship PR

Take the current branch to a **verified, review-ready draft PR** and drive CI green. The ceiling is review-ready — a human reviewer plus required CI do the merge, not this skill. Deterministic pipeline:

```
Stage 0: preflight   — repo / branch / base / remote; confirm a change exists; discover project gates
  ↓
Stage 1: exit gate   — /review-swarm (runs simplify, then the reviewer panel); resolve introduced ≥ MEDIUM
  ↓
Stage 2: local gates — typecheck + lint/format + changed-area tests (tiered by what changed)   → red = stop
  ↓
Stage 3: grep sweep  — whole repo incl. tests for every changed identifier; fix every sibling + caller
  ↓
Stage 4: commit+push — conventional commits, gt-first, NO Co-Authored-By
  ↓
Stage 5: draft PR    — from the repo template: Agent context + asked/built/deviated delta + review guide
  ↓
Stage 6: CI → green  — poll checks; classify flaky vs real; fix real, re-push; cap attempts + escalate
  ↓
Stage 7: hand back   — PR URL + draft state + green/red/deferred
```

## Hard rules

- **Never merge. Never `--admin`. Never bypass review.** The ceiling is a draft PR ready for review — stop there and hand back. Code owners + required CI are the gate. The ONLY exception is a solo-owned repo where the user has *explicitly* OK'd self-merge — never infer it from "CI is green."
- **Always `--draft`** (`gh pr create --draft`). Never open ready-for-review.
- **Never add `Co-Authored-By`** to commits.
- **Never skip Stage 1 (review gate) or Stage 3 (grep sweep)** to save time — skipping them is the documented #1 source of late-caught bugs (sibling tests, stale dates, local-pass/CI-fail).
- **Never push past a red local gate.** Fix it or stop and ask.
- **gt-first** — `gt create` / `gt submit`. If `gt submit` fails on a stack/restack conflict, STOP and ask; never resolve restack conflicts unilaterally or fall back to `git push` without approval.
- **Never force-push, rewrite pushed history, or delete branches** without an explicit ask. Add review fixes as standalone commits — don't squash them into existing ones.
- **Don't rerun CI to reroll the dice.** Batch fixes; push once per increment (CI credits).
- **Public-repo hygiene:** no private metrics, customer data, internal incidents, or Sentry references in commits, the PR body, or comments.

## Stage 0: preflight

1. Resolve repo root, current branch, and default branch (`git remote show origin` → `HEAD branch`, fallback `main`).
2. **Remote target:** if a PR already exists, check `gh pr view --json headRepositoryOwner` — some PRs track a fork, not `origin`. Push to the branch's actual remote.
3. Confirm there's a change: current branch ≠ default with commits, or a dirty tree. Nothing to ship → print `[ship-pr] No changes to ship.` and exit.
4. **Discover gates** (see table below) — read the project's CLAUDE.md `Commands`/`Lint` sections or detect by ecosystem. Don't hardcode.

## Stage 1: exit gate

Run **/review-swarm** (it runs `simplify` first, then the reviewer panel, and writes a graded HTML report; it's local-only and never posts to GitHub). Resolve every `introduced` finding at **MEDIUM or above**; surface the rest in the hand-back rather than silently fixing. If `review-swarm` isn't installed, fall back to `/simplify` + a senior-principal self-review of the diff. Never skip this stage to save time.

## Stage 2: local gates

Run the discovered gates, tiered by what changed. **Lean on CI for the full matrix — never run a huge monorepo suite locally.** A red gate is a hard stop: fix it (loop back through Stage 3 if you changed identifiers) or stop and ask. Never push past red.

| Project | Always (every push) | Conditional |
|---|---|---|
| **PostHog** | `ruff check . --fix` + `ruff format .`; `pnpm --filter=@posthog/frontend typescript:check`; `hogli test <changed area>` | serializer/viewset → `hogli build:openapi`; migration → migration-safety check; frontend build → `pnpm --filter=@posthog/frontend build` |
| **Generic** | detect pm (uv/pnpm/cargo/go); typecheck + lint/format + changed-area tests | schema → regen types; migration → safety check; frontend → build |

## Stage 3: grep sweep (the #1 lesson)

Before pushing, `grep -rn` the **whole repo — app code AND tests** — for every identifier, string, prop, route, version, or status code you changed, and update every sibling test and caller. "Changed-file tests passed locally" ≠ full suite green. This is the single highest-yield step against CI-red.

## Stage 4: commit + push

- Conventional-commit subject: lowercase, no trailing period, **< 72 chars**; scope optional (`llma` for LLM-analytics changes). Body explains what + why.
- **No `Co-Authored-By`.**
- `gt create` for the branch, `gt submit --draft` to push + open. If `gt submit` hits a stack/restack conflict → STOP and ask.
- **Push may be blocked** (Secretive secure-enclave key needs Touch ID and refuses in-session). If push fails for signing/auth reasons, verify the branch fast-forwards cleanly, then hand the user the exact push/submit command and continue once they confirm — don't retry or token around it.

## Stage 5: draft PR

- **Read `.github/pull_request_template.md` first** if present and use its exact section structure — don't invent a format.
- Fill the **Agent context** section, an **asked / built / deviated+why** delta, and a **review guide** (tests-first reading order; load-bearing vs mechanical split). Add a `mermaid` diagram only when it clarifies a non-trivial change.
- Pass the body straight to `gh pr create --draft --body-file -` via stdin — don't write a temp file.
- If a PR already exists, **don't overwrite its body wholesale** (clobbers user-added screenshots) — anchor-splice into the existing body.

## Stage 6: CI → green

1. Poll `gh pr checks <pr>` (read-only — reads existing run state, doesn't burn credits). Use `--watch` with a timeout, or loop with a sensible interval and a cap.
2. Red job → `gh run view <id> --log-failed`. **Classify** real failure vs flaky vs infra (on PostHog: lean on the `debugging-ci-failures` skill + `hogli ci:insights`; for flakes, `fixing-flaky-tests`).
3. **Real failure** → fix locally, re-run the relevant Stage-2 gate, re-run Stage 3 if identifiers moved, push one batched increment, continue.
4. **Flaky / infra** → note it honestly; never mask with sleeps/retries/bigger timeouts; don't blind-rerun.
5. **Cap:** after ~3 fix cycles, or on a genuine design fork, STOP — summarize what's red and why, and ask (AskUserQuestion). Never grind indefinitely.
6. Green ≠ done: still hand back review-ready. **Never merge.**

## Stage 7: hand back

Report: PR URL, draft state, CI summary (green / red / pending per check), anything deferred, and the asked/built/deviated delta. Then stop — the human reviews and merges.

## Graceful degradation

- `review-swarm` / `simplify` not installed → `/simplify` + self-review, note it.
- `gt` not set up on the repo → plain `git` branch + commit, ask before pushing.
- No PR template → a clean honest body (what + why + gate results + delta).
- CI not configured on the repo → skip Stage 6, note "no CI to wait on."

## Rationalization table — STOP if you catch yourself here

| Excuse | Reality |
|---|---|
| "Tiny change, skip review-swarm" | Tiny changes are where late bugs hide. Run it. |
| "CI is green, I'll just merge it" | Not your call — code owners review. Hand back review-ready. |
| "Changed-file tests pass, skip the grep sweep" | That's the documented #1 cause of CI-red. Sweep the whole repo. |
| "Local gate is red but it's unrelated" | Red is a stop. Fix it or ask — don't push past it. |
| "`gt submit` conflicted, I'll `git push`" | STOP and ask. Never resolve restack conflicts unilaterally. |
| "Open it ready-for-review to save a click" | Always `--draft`. |
| "CI's been flaky, just rerun until green" | Classify the failure. Don't reroll dice or mask flakes. |

## Red flags — STOP and re-read the Hard rules

- About to run `gh pr merge`, `--admin`, or `--ready`.
- About to skip Stage 1 or Stage 3.
- About to push past a red local gate.
- About to force-push, rewrite pushed history, or delete a branch without asking.
- About to write the PR body to a temp file, or overwrite an existing PR body wholesale.
