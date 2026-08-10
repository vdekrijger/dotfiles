# Phase-3 build subagent dispatch template

Fill in the `<...>` placeholders from the verified contract (Phase 1) and usage flows (Phase 2),
then dispatch as a background subagent in an isolated git worktree (one PR).

---

**Goal:** Add the `posthog_<thing>` resource to terraform-provider-posthog, end-to-end, to a
review-ready **draft PR**. <one-line description of what the resource manages>

**READ FIRST (before editing):**
- `internal/resource/experiment.go` + `internal/resource/experiment_test.go` — the most complete
  resource reference (GenericResource + Ops, JSON normalization, transition/stub-client tests).
- `internal/httpclient/experiment.go` + its test — request/response structs, CRUD, sub-actions,
  soft-delete.
- `internal/resource/core/` — the GenericResource framework + base models + import parser.
- An existing `examples/resources/posthog_*/` for the example + import.sh convention.

**Verified API contract:** <paste the Phase-1 contract.md: paths, verbs, fields (name/type/
read-only/writable), enums, delete semantics, sub-actions, and the create-vs-update parity notes>

**Target usage flows (become acceptance tests + example):** <paste the 2-3 HCL flows from Phase 2>

**Deliverables (a test per behavior):**
1. `internal/httpclient/<thing>.go` — response + request structs (pointers/omitempty), CRUD
   (soft-delete via PATCH if hard DELETE is forbidden), any sub-action methods, a narrow interface
   for sub-action sequencing.
2. `internal/resource/<thing>.go` — `GenericResource` wiring + `Ops`: Schema (enum validators,
   field taxonomy: two-way / config-only / RequiresReplace; JSON-blob fields as
   `jsontypes.Normalized`; required nested blocks enforced in `ModifyResourcePlan`), Build*Request
   (shared field mapping helper — **every writable field on both create and update**),
   MapResponseToModel (two-way read-back; leave config-only untouched), CRUD.
3. Unit tests: Build*Request mapping, MapResponseToModel (two-way + config-only + import),
   sub-action sequencing via stub client, httpclient httptest.
4. Acceptance tests (`testacc/<thing>_test.go`): full lifecycle + CheckDestroy, drift
   (RefreshState + ExpectNonEmptyPlan), idempotency (PlanOnly), raw-API outcome checks.
5. `examples/resources/posthog_<thing>/{resource.tf,import.sh}`; run `make generate` and commit
   the regenerated docs.

**Before pushing:**
- `grep -rn` the whole repo (app + tests) for every identifier/field/route you touched; update
  every caller and sibling test.
- Gates: `gofmt -l` (clean), `go vet ./...`, `go build ./...`, `go test ./internal/...`,
  `terraform fmt` the examples.
- Commit: conventional message, **no Co-Authored-By**, signed (`export GPG_TTY=$(tty)`), open a
  **draft** PR. Never merge.

**Report back (data for the controller, not prose):** PR number, files changed, gate results
(pass/fail each), any behavior deferred or assumption made, and anything that needs a live-stack
run to confirm (the controller runs Phase 4 e2e).
