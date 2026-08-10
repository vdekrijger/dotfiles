# Design — `implementing-posthog-tf-resource` skill

**Status:** approved design, pre-implementation
**Date:** 2026-08-10

## Purpose

A self-contained, user-invoked skill that adds a new resource to `terraform-provider-posthog`
end-to-end — from live-API verification through a review-ready draft PR — encoding the
conventions and hard-won learnings from building `posthog_experiment`.

The defining principle: **verify against a live PostHog stack before writing code and again
after** (empirical API contract + staged example run). This is what caught real bugs that unit
and acceptance tests missed this session.

## Scope & decomposition

In scope: **one skill** that builds one PostHog TF provider resource per invocation.

Explicitly out of scope (separate, thinner skills to build later — they mostly orchestrate
existing skills like `hey-bud`, `review-swarm`, `ship-pr`):

- **Third-party PR triage** — review + verify an external contributor's PR.
- **Issue implementation** — turn a GitHub issue into a PR.

A short sketch of both is included at the end so their small net-new surface is visible, but
neither is built here.

## Key decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Composition | **Fully self-contained** | Stands alone; won't break when other skills change (accepts some drift). |
| Live-stack verification | **Hard gate at both ends** | No plausible-but-unverified code; no "done" without a staged e2e run. Caught the `allow_unknown_events` bug. |
| Execution | **Subagent-driven, one PR** | Matches the CLAUDE.md default; keeps the main loop lean. |
| Design method | **Usage-first** | Sketch realistic HCL flows first; the schema follows from what makes them clean. |
| Example flow | **First-class, peer of testacc** | The staged example run is a bug-surfacing tool, not a demo. Use realistic inputs so it can fail. |

## Frontmatter

```yaml
name: implementing-posthog-tf-resource
user_invocable: true
disable-model-invocation: true
description: Use when invoked as /implementing-posthog-tf-resource <resource> to add a new
  resource to terraform-provider-posthog end-to-end — live-API verification, GenericResource +
  httpclient scaffolding, unit + acceptance tests, a realistic flow example run staged against a
  live stack, docs, and a review-ready draft PR. Never merges.
```

## Phase flow

`✋` = hard gate that stops and asks rather than proceeding.

| # | Phase | Where | Gate |
|---|-------|-------|------|
| 0 | **Intake** — resource name, API surface, live-stack host + key | main loop | ✋ no reachable stack + key → stop |
| 1 | **API discovery & verification** — hit the real endpoints; record the contract (paths, field names, enums, sub-actions, quirks) into a scratch `contract.md`. Includes the **create-vs-update field-parity check**: for every writable field, confirm it is accepted on *both* create and update. | main loop, live stack | ✋ contract unverified → do not code |
| 2 | **Usage-first design** — sketch 2-3 realistic HCL usage flows first; derive the schema (field taxonomy: two-way / config-only / create-only / RequiresReplace; JSON-blob fields; lifecycle block) from what makes those flows clean. | main loop | design noted |
| 3 | **Build** — dispatch a background subagent in an isolated worktree that takes it end-to-end: httpclient layer + `GenericResource` + `Ops` + JSON normalization + unit tests + acceptance tests + `make generate`; runs gates + grep-before-push; opens a **draft** PR. | subagent | subagent reports gate results |
| 4a | **Author flow example(s)** — `examples/<topic>/main.tf` for the common flows from Phase 2, using **realistic events (never `$pageview`)** so validation can actually trip. | main loop | — |
| 4b | **Playground e2e (staged)** — build binary, `dev_overrides`, drive the *full lifecycle* via staged applies; verify outcomes via raw API; check idempotency (`PlanOnly`); destroy; clean up orphans. **Treat any divergence as a bug to fix, not a demo to tweak.** | main loop, live stack | ✋ e2e not green → not done |
| 5 | **Self-review & report** — gofmt / go vet / terraform fmt, unit + acceptance results, asked/built/deviated delta. | main loop | — |

## Embedded knowledge payload

The skill ships a `references/` dir so the knowledge is durable, not just prose.

### `references/conventions.md` — the repeatable how

- `GenericResource[TFModel, APIReq, APIResp]` + the `ResourceOps` interface members: `Schema`,
  `BuildCreateRequest`, `BuildUpdateRequest`, `MapResponseToModel`, `Create`/`Read`/`Update`/`Delete`,
  `ResourceName`, optional `ResourcePlanModifier`.
- httpclient layer pattern: request/response structs, CRUD methods, sub-action POSTs,
  soft-delete via `PATCH {deleted:true}`.
- JSON-blob fields → `jsontypes.Normalized` + the shared whitelist normalizer (keep only
  user-declared fields) to avoid perpetual diff.
- Field taxonomy: **two-way vs config-only vs create-only**; `RequiresReplace`; enum validation
  via `stringvalidator.OneOf`.
- `SingleNestedBlock` "required-block" idiom: the framework can't mark a block required; enforce
  in `ModifyResourcePlan` for one clear diagnostic.
- Testing patterns: unit (`BuildCreate/UpdateRequest`, `MapResponseToModel`, **stub-client
  interfaces** for lifecycle sequencing); acceptance (`TF_ACC`, `CheckDestroy`, drift via
  `RefreshState` + `ExpectNonEmptyPlan`, `PlanOnly` idempotency, **raw-API outcome checks**).
- Example conventions: `examples/resources/<name>/{resource.tf,import.sh}` + a narrated flow
  example under `examples/<topic>/main.tf`.

### `references/gotchas.md` — the traps

- **create-vs-update field parity** (the `allow_unknown_events` bug): a create-only field that the
  API re-validates on update breaks any later edit/launch. Dedicated checklist item.
- Non-atomic multi-step operations → name the live state in the error so a partial failure is
  recoverable.
- `export GPG_TTY=$(tty)` so signed commits don't fail from a non-interactive shell.
- zsh alias collisions in helper scripts (`st`, `status` are taken).
- testacc env vars (`POSTHOG_HOST`, `POSTHOG_API_KEY`, `POSTHOG_PROJECT_ID`,
  `POSTHOG_ORGANIZATION_ID`); stale-key handling; "migrations not up to date" is usually benign.
- playground `dev_overrides` setup; clean up auto-created orphan flags after a bare-key run.
- commit/PR rules: draft PRs only, no `Co-Authored-By`, conventional commits, fast-forward or `gt`.

## Files shipped

```
dotfiles/ai/skills/implementing-posthog-tf-resource/
├── SKILL.md                       # frontmatter + phase flow (0-5), gates, dispatch
├── DESIGN.md                      # this document
├── references/
│   ├── conventions.md
│   └── gotchas.md
└── templates/
    └── build-subagent-prompt.md   # Phase-3 dispatch template: goal (+ root cause), READ-FIRST
                                    # files, numbered deliverables, grep/gate rules, report-back
```

Symlink `~/.claude/skills/implementing-posthog-tf-resource → dotfiles/ai/skills/…` to match the
other skills. Commit in the **dotfiles** repo (personal tooling), on a clean branch off `main`
via `gt` — never into the public provider repo.

## Success criteria

- Invoking `/implementing-posthog-tf-resource <resource>` with a reachable stack produces a
  review-ready draft PR: resource + httpclient + unit + acceptance tests + example + docs.
- The skill refuses to write resource code without a verified API contract, and refuses to
  report "done" without a green staged playground run.
- The create-vs-update parity check is an explicit step.
- No merge; stops at the draft PR (autonomy ceiling).

## Non-goals (YAGNI)

- No holdout/other-resource management beyond referencing existing IDs.
- No generic feature-building logic that duplicates `hey-bud`.
- Not building the PR-triage or issue-implementation skills here.

## Appendix — sketch of the two follow-on skills

**`triage-posthog-pr`** (future): fetch an external PR → run `review-swarm` (or the cloud
review) → verify the diff builds + tests pass locally in a worktree → post a decision summary.
Mostly orchestration over existing review skills; net-new is the fetch + local-verify glue.

**`implement-posthog-issue`** (future): read a GitHub issue → if it's a new resource, delegate to
this skill; otherwise run the `hey-bud` brainstorm→build→review flow scoped to the issue → draft
PR that closes it. Net-new is issue parsing + routing.
