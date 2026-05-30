# Temporal Alert Timeliness SLO Emission Pitfalls

Session-derived notes for implementing PostHog alert-check timeliness SLOs in Temporal workflows.

## Temporal side effects

Do not emit analytics/SLO events directly from workflow code. Workflow code must remain deterministic and replay-safe; direct analytics calls can duplicate on replay/task retry and can make side effects happen outside Temporal's activity model.

Preferred shape:

1. `retrieve_due_alerts` snapshots the original due timestamp before any schedule mutation.
2. Workflow input carries that snapshot as `scheduled_check_at`.
3. Workflow calls a dedicated activity such as `emit_alert_timeliness_slo` before normal alert evaluation.
4. The activity calculates current lag using activity-time wall clock and emits started/completed SLO events.
5. The activity catches/logs/captures its own emission failures so alert evaluation is not blocked by observability failures.
6. The workflow also treats the activity as best-effort; if it fails after retries, continue with the alert check and log the observability failure.

## Denominator and outcomes

- `scheduled_check_at is None` means initial/no-due work. Exclude it from the timeliness SLO denominator; do not emit a success.
- A late check that eventually evaluates successfully is two facts:
  - alert execution SLO: success
  - alert timeliness SLO: failure
- Preserve both facts; do not let query success mask scheduler lateness.

## Test patterns

- Unit-test threshold math independently from Temporal.
- Test timestamp parsing for `Z`, timezone offsets, and naive timestamps.
- Test `retrieve_due_alerts` preserves original `next_check_at` before `add_alert_check` mutates schedule state.
- Test the dedicated emission activity directly with mocked analytics.
- For async DB tests that cross activity/thread boundaries, use transaction-aware Django DB tests where required so the activity sees setup rows.
- Workflow tests should register the timeliness emission activity along with existing alert activities, then assert both execution and timeliness SLO events for late-but-successful checks.

## Local proof artifacts

If you create local criteria/proof notes inside a worktree, keep them out of the PR unless the repo expects that documentation. Prefer a non-committed scratch path or delete the artifact before final status/PR prep.
