---
name: implementing-posthog-tf-resource
user_invocable: true
disable-model-invocation: true
description: Use when invoked as /implementing-posthog-tf-resource <resource> to add a new resource to terraform-provider-posthog end-to-end — live-API verification, GenericResource + httpclient scaffolding, unit + acceptance tests, a realistic flow example run staged against a live stack, docs, and a review-ready draft PR. Never merges.
---

# Implementing a PostHog Terraform Resource

Add one new resource to `terraform-provider-posthog`, end-to-end, to a review-ready **draft PR**.

**Core principle: verify against a live PostHog stack before writing code and again after.** An
empirical API contract (Phase 1) and a staged example run (Phase 4) are hard gates — they catch
bugs that unit and acceptance tests miss. Do not skip them.

**Flow:** 0 Intake → 1 Verify API (✋) → 2 Usage-first design → 3 Build (subagent, one PR) →
4 Example + staged e2e (✋) → 5 Self-review & report. Never merge — stop at the draft PR.

Create one todo per phase and work them in order.

## Phase 0 — Intake

Collect and confirm before anything else:
- The **resource name** (`posthog_<thing>`) and its PostHog REST API surface (collection path,
  item path, any sub-action endpoints).
- A **reachable live stack**: `POSTHOG_HOST`, a personal `POSTHOG_API_KEY`, `POSTHOG_PROJECT_ID`
  (and `POSTHOG_ORGANIZATION_ID` if project-scoped). Confirm reachability with one authenticated
  GET.

✋ **Gate:** no reachable stack + valid key → stop and ask. Everything downstream depends on it.

## Phase 1 — API discovery & verification

Hit the real endpoints with `curl` and record the contract to a scratch `contract.md`
(scratchpad, not the repo):
- Exact paths (collection, item, sub-actions) and HTTP verbs.
- Every field: name, type, required/optional, read-only vs writable.
- Enums — capture the actual accepted values.
- Delete semantics (hard DELETE vs soft-delete via `PATCH {deleted:true}` — many PostHog
  resources forbid hard delete with a 405).
- **Create-vs-update field parity:** for every writable field, confirm the API accepts it on
  BOTH create and update. A create-only field the API re-validates on update is a bug waiting to
  happen (this is the `allow_unknown_events` class of bug). Note any field that must ride along on
  updates.

✋ **Gate:** do not write resource code until the contract is empirically verified. No
plausible-looking code from memory or docs alone.

See `references/conventions.md` for how the contract maps onto the resource layer.

## Phase 2 — Usage-first design

Design from how a user would actually write it, not from the API shape:
- Sketch **2-3 realistic HCL usage flows** first (the common journeys). Let the schema fall out
  of what makes those flows clean and idiomatic.
- Decide the **field taxonomy** for each field: two-way (sent + read back), config-only (sent,
  not read back), create-only (`RequiresReplace`). Get this right — it drives
  `MapResponseToModel` and drift behavior.
- JSON-blob fields → `jsontypes.Normalized` + whitelist normalizer.
- Lifecycle/nested blocks → remember the `SingleNestedBlock` required-block idiom (enforce in
  `ModifyResourcePlan`).

Write the chosen usage flows down — they become the acceptance tests and the flow example.

## Phase 3 — Build (subagent, one PR)

Dispatch a background subagent in an isolated git worktree to take the resource end-to-end. Use
`templates/build-subagent-prompt.md` as the dispatch prompt, filled in with the verified contract
and the usage flows. It must deliver: httpclient layer, `GenericResource` + `Ops`, JSON
normalization, unit tests, acceptance tests, `make generate`, all gates green + grep-before-push,
and a **draft** PR.

Keep the main loop lean; coordinate, don't implement. When it reports back, verify its gate
results before proceeding.

## Phase 4 — Example + staged e2e

This is a peer of the acceptance suite, not an afterthought. It surfaces bugs the tests miss.

**4a — Author the flow example** (`examples/<topic>/main.tf`) covering the Phase-2 usage flows.
Use **realistic events/inputs, never `$pageview`** — realistic inputs are what let the example
actually fail and expose validation bugs.

**4b — Run it staged against the live stack:** build the provider binary, set up `dev_overrides`,
and apply the example **stage by stage** through the full lifecycle. After each stage, verify the
real outcome via the raw API (not just TF state). Check idempotency with a `PlanOnly` re-plan.
Then `destroy` and clean up any orphaned resources (e.g. auto-created flags).

✋ **Gate:** any divergence from expected behavior is a **bug to fix in the code**, not a demo to
tweak. Not done until the staged run is green end-to-end. If a fix is needed, loop back to
Phase 3.

## Phase 5 — Self-review & report

- Gates: `gofmt -l`, `go vet`, `terraform fmt`, unit + acceptance results.
- Report an **asked / built / deviated** delta.
- Confirm the PR is a **draft** and stop. Never merge (autonomy ceiling = review-ready draft PR).

## Reference material

- `references/conventions.md` — the repeatable how (framework, httpclient, normalization, tests,
  examples).
- `references/gotchas.md` — the traps this pattern has already hit; read before you push.
- `templates/build-subagent-prompt.md` — the Phase-3 dispatch template.
