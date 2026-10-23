# Conventions — terraform-provider-posthog resources

The repeatable "how" for adding a resource. Read alongside an existing resource
(`internal/resource/experiment.go` is the most complete reference).

## Resource layer — GenericResource + Ops

Resources are built on a generic framework, not hand-rolled CRUD:

```go
func NewThing() resource.Resource {
    return core.NewGenericResource[ThingTFModel, thingAPIRequest, httpclient.Thing](
        ThingOps{},
        core.ProjectScopedImportParser[ThingTFModel](),
    )
}
```

Implement the `ResourceOps` interface on `ThingOps`:
- `ResourceName() string`
- `Schema() schema.Schema`
- `BuildCreateRequest(ctx, model) (apiRequest, diag.Diagnostics)`
- `BuildUpdateRequest(ctx, plan, state) (apiRequest, diag.Diagnostics)`
- `MapResponseToModel(ctx, resp, *model) diag.Diagnostics`
- `Create` / `Read` / `Update` / `Delete`
- Optional `ResourcePlanModifier` → `ModifyResourcePlan(ctx, req, resp)` for cross-field or
  required-block validation.

Embed `core.BaseInt64Identifiable` and `core.BaseProjectID` in the TF model. Share create/update
field mapping in one helper (e.g. `applyCommonThingFields`) so create and update can't drift —
see the parity gotcha.

## httpclient layer

One file per resource under `internal/httpclient/`. Define a response struct (`Thing`) and a
request struct (`ThingRequest`, all pointers/`omitempty` so PATCH sends only what changed). CRUD
methods: `CreateThing`, `GetThing` (returns `HTTPStatusCode`), `UpdateThing` (PATCH),
`DeleteThing`. Sub-actions are dedicated POST methods to `.../<action>/`.

**Soft-delete:** many PostHog resources 405 on hard DELETE. Implement `DeleteThing` as
`UpdateThing(ctx, id, {Deleted: &true})`, sending only `deleted`. In `Read`, map a returned
`deleted=true` to `http.StatusNotFound` so Terraform recreates rather than silently tracking a
deleted resource.

**Sub-action sequencing:** when a resource has ordered sub-actions (launch/pause/…), define a
narrow interface for just those methods so the sequencer is unit-testable with a stub client.

## JSON-blob fields

For free-form JSON (metrics, filters, criteria): type the schema attribute as
`jsontypes.NormalizedType{}` and the model field as `jsontypes.Normalized`. On read, normalize the
API blob against the configured value with the shared whitelist normalizer (keep only
user-declared keys) so reordered keys and server-computed fields (uuid, fingerprint) don't
produce a perpetual diff. Mark such attributes `Optional + Computed`.

## Field taxonomy

Classify every field — it determines `MapResponseToModel` and drift:
- **two-way** — sent on write AND read back. Out-of-band edits surface as drift.
- **config-only** — sent on write, NOT read back (API doesn't echo it). Leave untouched in
  `MapResponseToModel`.
- **create-only** — set once; `RequiresReplace` plan modifier. The linked-flag key, etc.

Validate enums in the schema with `stringvalidator.OneOf(values...)`. Keep the accepted-value
list in one `var` shared by the validator and any logic.

## Required nested blocks

The framework has no "required block" flag. If a `SingleNestedBlock` (and an attribute inside it)
must be present, mark the attribute `Optional` and enforce presence in `ModifyResourcePlan` with a
single clear diagnostic. Skip the check when `req.Plan.Raw.IsNull()` (destroy).

## Tests

**Unit** (`internal/resource/<thing>_test.go`, `internal/httpclient/<thing>_test.go`):
- `BuildCreateRequest` / `BuildUpdateRequest` field mapping + any transition table.
- `MapResponseToModel` — two-way read-back and config-only preservation; import from empty model.
- Sub-action sequencing via a **stub client** implementing the narrow interface (ordering +
  mid-sequence failure naming the failed action).
- httpclient: httptest server asserting method, path, body, and soft-delete sends only `deleted`.

**Acceptance** (`testacc/<thing>_test.go`, `TF_ACC`):
- Full lifecycle + `CheckDestroy`.
- Drift: mutate out-of-band via the raw client, then `RefreshState` + `ExpectNonEmptyPlan`.
- Idempotency: a `PlanOnly` step after apply must be empty.
- **Outcome checks via the raw API** (not just TF state) for anything the resource causes
  server-side (e.g. a shipped variant rewriting a flag's distribution).

## Examples & docs

- `examples/resources/posthog_<thing>/resource.tf` + `import.sh` — feeds the auto-generated
  resource doc page (`make generate`).
- A narrated flow example under `examples/<topic>/main.tf` for the common journeys (see the
  experiments example) — matches the `examples/rbac`, `examples/feature-flags` convention.
- Run `make generate` after any schema/description change; commit the regenerated docs.
