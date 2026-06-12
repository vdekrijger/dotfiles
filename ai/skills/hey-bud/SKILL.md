---
name: hey-bud
disable-model-invocation: true
description: Use when the user invokes /hey-bud to build a feature end-to-end — from brainstorming through implementation, code review, cleanup, and Graphite branch stacking.
---

# Hey Bud — End-to-End Feature Builder

Build a feature from idea to merge-ready code in one session.

**Flow:** 1 Brainstorm → 2 Surface decisions (loop until the user resolves all) → 3 Write plan → 4 Create branch → 5 Execute plan → 6 Simplify → 7 Code review (loop: fix issues until grade ≥ B+/A−) → 8 Stack branches → 9 Final report

## Phases

### 1. Brainstorm

Invoke `superpowers:brainstorming` — full flow: explore context, clarifying questions one at a time, 2-3 approaches, present design, write spec. Offer visual companion for UI work.

### 2. Surface Decisions

After the spec, BEFORE the plan: extract every point where the user might have a strong opinion, as a numbered list with a recommendation each — tradeoffs with no obvious winner (sync vs async), edge-case behavior (what if X is deleted/missing?), UX choices (placement, wording, error messages), scope boundaries (include adjacent thing or defer?), anything two reasonable engineers would disagree on.

Format:

> Here are the decisions I'd like your input on:
>
> 1. **[Decision]** — [options]. I'd lean [X] because [reason].
>
> Everything else is implementation detail. Which of these do you want to weigh in on?

Keep asking until the user confirms all decisions are resolved. Update the spec with their answers.

### 3. Write Plan

Invoke `superpowers:writing-plans` on the finalized spec, including the plan review loop.

### 4. Create Branch

Create a feature branch BEFORE executing — ask for or suggest a name. Do NOT commit to master.

### 5. Execute Plan

Invoke `superpowers:subagent-driven-development`: task-by-task, fresh subagents, two-stage review (spec compliance + code quality) per task.

### 6. Simplify

Invoke the `simplify` skill on all changed code (reuse, quality, efficiency); fix findings.

### 7. Code Review Loop

Dispatch the `code-reviewer` agent on the full implementation; it must grade. **Quality gate: B+/A− or higher.** If below: fix every critical/important finding, re-run the reviewer, repeat until the gate passes. Track fixes per iteration for the final report.

### 8. Stack Branches with Graphite

1. Review commit history (`git log --oneline`)
2. Propose grouping commits into independently reviewable PRs. Good boundaries: backend model/logic; backend API + tests; frontend + tests; each independent feature
3. Present for approval:
   > I'd split this into N stacked PRs:
   >
   > 1. **PR title** — commits X, Y (description)
   >
   > Does this split make sense?
4. Once approved: `gt create` each branch, `gt submit` the PRs, follow `.github/pull_request_template.md`

Single-PR preference: skip stacking, `gt create` + `gt submit` the whole branch. Unfamiliar with the repo's Graphite setup: ask how the user stacks before assuming.

#### Public-OSS PR body safety

Before `gt submit` (or `gh pr create`/`edit`), check the PR body — these must NEVER ship in a public repo:

- **No internal operational metrics** — team/event counts, failure-rate percentages, latency p99s, customer numbers, "we observed X" stats — even when produced by a tool the user ran (slo-failures-daily, dashboards, prod queries). Summarize high-level: "polluting the SLO failure-rate signal", not "211 events / 7 days from 34 teams".
- **No customer or incident references** — names, internal Slack threads, incident IDs.
- **No unreleased roadmap details** not already public.
- **Verify claims against the actual diff** — bodies drift mid-iteration; cross-check named functions, paths, and behavior claims at the branch tip.
- **Match `.github/pull_request_template.md` structure** — sections are guardrails for what to include, not a license to dump everything.

Enforced by `AGENTS.md` lines 70-77 in the PostHog repo. Pretend a contributor with zero internal context is reading — cut anything relying on private knowledge.

### 9. Final Report

```
## Feature Complete
**Branch:** [name]  **Grade:** [final grade]  **PRs:** [links, or "ready to submit"]
### What was built          — bullet per feature/change
### Design decisions made   — each phase-2 decision + choice + why
### Issues found and fixed during review — per iteration
### Files changed           — grouped: backend, frontend, tests
### Test results            — backend: X passed / frontend: X passed
```

## Rules

- **Never commit to master.** Branch first.
- **Never push** unless the user explicitly asks.
- **Never skip decision surfacing** — present at least the top 3 even if everything seems obvious.
- **Never skip simplify**, even if the code looks clean.
- **Never accept below B+/A−.** Keep looping.
- **Track everything** — the final report must include all design decisions and all review fixes, so the user knows what tradeoffs were made on their behalf.
- **Always propose the branch stack** before executing; let the user adjust the split.
