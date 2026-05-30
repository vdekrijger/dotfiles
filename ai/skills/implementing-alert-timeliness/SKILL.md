---
name: implementing-alert-timeliness
description: Use when implementing or reviewing PostHog alert-check timeliness, scheduler lateness, due-work SLOs, alert backlog dashboards, or alert-check observability in PostHog.
---

# Implementing Alert Timeliness

Build alert-check timeliness as a separate SLO from alert execution. The proof target is: operators can tell whether checks started close to their scheduled due time, even when the eventual query succeeds.

## Core Principle

Execution success is not timeliness success. A check that starts too late is an SLO failure even if the alert query later succeeds.

## Mode Selection

Use the full pipeline for new SLO instrumentation, dashboard/Terraform work, or changes touching scheduler + evaluator + SLO wiring. Use review mode when assessing an existing diff.

| Signal | Full implementation | Review only |
|---|---:|---:|
| Adds `SloOperation` or alert timing events | yes | |
| Changes alert scheduling/evaluation flow | yes | |
| Adds dashboard/Terraform/query panels | yes | |
| Reviewing an already-written PR | | yes |
| Only answering conceptual SLO threshold questions | | yes |

## Full Pipeline

1. Discover current state
   - Read PostHog alert scheduling and evaluation paths before editing.
   - Known anchors: `posthog/temporal/alerts/schedule.py`, `posthog/temporal/alerts/activities.py::retrieve_due_alerts`, `posthog/tasks/alerts/utils.py::add_alert_check`, and `posthog/slo/`.
   - If live PostHog MCP access is available, query current alert telemetry before choosing thresholds or dashboard language.

2. Define the SLI contract
   - Eligible event: an existing scheduled alert check with a non-null due timestamp.
   - Good event: worker/evaluator starts within the threshold from that original due timestamp.
   - Bad event: starts after threshold, times out before start, is skipped because of backlog, or is missing from expected due-work accounting.
   - Exclude initial/no-schedule checks (`next_check_at is None`) from the denominator. Do not emit success for them.

3. Choose the threshold
   - Preferred formula:

     ```text
     allowed_lag = clamp(interval_seconds * 0.05, min=60s, max=120s)
     ```

   - Rationale: future 1-minute alerts get one scheduler tick of grace; 15-minute alerts stay at the 60s floor; hourly alerts allow 180s by pure percentage but cap at 120s, and daily/weekly/monthly alerts also cap at 120s so long intervals cannot hide backlog.
   - 10% is too lenient for the agreed PostHog alert timeliness SLO unless product/SRE explicitly revises the target.
   - Avoid 5-minute caps unless the SLO target intentionally tolerates multi-minute alert lateness.

4. Write criteria before code
   - REQ-TIME-1: Timeliness has a distinct `SloOperation` / event name from execution success.
   - REQ-TIME-2: The original due timestamp is snapshotted before `add_alert_check` or any path mutates `next_check_at`.
   - REQ-TIME-3: Late-but-successful checks emit timeliness failure and execution success.
   - REQ-TIME-4: No-due initial checks are excluded, not counted as successful.
   - REQ-TIME-5: Threshold calculation covers 1m, 15m, hourly, daily, weekly, and monthly intervals without `relativedelta` ambiguity.
   - REQ-TIME-6: Dashboard/Terraform/query visibility is included or explicitly deferred in the plan/PR.

5. Implement with TDD
   - Write failing tests for threshold calculation first.
   - Write failing tests for due timestamp snapshotting before mutation.
   - Write failing tests proving late success is classified as timeliness failure.
   - Write failing tests proving no-due checks do not inflate the success denominator.
   - When asserting SLO payload fields that depend on deployment config (for example `region` from `get_instance_region()`), patch the config helper in the test (`@patch("posthog.temporal.alerts.activities.get_instance_region", return_value="US")`) instead of relying on CI environment defaults. CI may legitimately return `None`, making an otherwise valid SLO test flaky/red.
   - Then implement the smallest code needed to pass.

6. Wire observability
   - Suggested event fields: `alert_id`, `insight_id`, `team_id`, `calculation_interval`, `scheduled_due_at`, `actual_check_start_at`, `evaluation_lag_ms`, `timeliness_threshold_ms`, `is_late`.
   - Keep high-cardinality labels out of metrics if the backend cannot tolerate them; event properties are usually safer for exploratory HogQL than metric labels.
   - Keep execution SLO fields/events separate from timeliness fields/events.
   - In Temporal code, emit timeliness SLOs from a dedicated best-effort activity, not directly from workflow code. Direct workflow-side analytics can duplicate on replay/task retry and should not be able to block alert evaluation. See `references/temporal-slo-emission-pitfalls.md`.

7. Prove with live-style queries
   - Dashboard should show on-time percentage, late percentage, p50/p90/p99 lag, current backlog, and split by interval/source where useful.
   - For PostHog MCP/HogQL: discover schema first; include `LIMIT 100`; do not print secrets.
   - Useful existing telemetry while developing: `alert check backlog`, `poc_alerting_pipeline_health`, `poc_alerting_exception_run_summary`, `poc_alerting_ticket_run_summary`.

8. Review hardening
   - Run SRE review against the diff and explicitly ask: “Could this query succeed late and still look green?”
   - Run normal test suite plus targeted alert/SLO tests.
   - If dashboard/Terraform is deferred, the PR must say what follow-up will make the SLO visible.

## Review Mode Checklist

Flag the diff if any answer is “no”:

1. Is alert-check timeliness separate from alert-check execution success?
2. Is the scheduled due timestamp captured before it can be mutated?
3. Does too-late count as failure even when evaluation succeeds?
4. Are initial/no-due checks excluded from the denominator?
5. Does the threshold avoid hiding long-interval backlog?
6. Is there visible dashboard/SLO wiring, or an explicit deferral?
7. Can operators query current split/backlog without reading application logs?

## Current Query Pattern

When live data is available, compute both backlog and duration split. Backlog answers “are checks waiting?”; duration answers “is the pipeline slow?” Neither replaces the dedicated SLO, but both ground the rollout.

```sql
SELECT
  multiIf(
    toFloat(properties.backlog) = 0, '0 backlog',
    toFloat(properties.backlog) <= 2, '1-2 backlog',
    toFloat(properties.backlog) <= 10, '3-10 backlog',
    '>10 backlog'
  ) AS bucket,
  count() AS checks,
  round(100 * checks / sum(checks) OVER (), 2) AS pct
FROM events
WHERE event = 'alert check backlog'
  AND timestamp >= now() - INTERVAL 30 DAY
  AND properties.backlog IS NOT NULL
GROUP BY bucket
ORDER BY min(toFloat(properties.backlog))
LIMIT 100
```

## Common Failure Modes

| Failure | Why it is wrong | Fix |
|---|---|---|
| Reuse execution success as timeliness | Late successful checks look healthy | Add separate timeliness operation/outcome |
| Measure only completion | Conflates queue delay with evaluation duration | Capture due, start, and completion separately |
| Read `next_check_at` after evaluation | `add_alert_check` may mutate it | Snapshot original due time first |
| Count first/no-due checks as success | Inflates denominator | Exclude or track separately |
| Threshold is 10% or percentage-only | Daily/monthly checks hide hours of lateness; 10% is looser than the agreed SLO | Use 5% with 60s floor and 120s cap |
| Instrumentation without dashboard | Operators cannot use it | Add Terraform/dashboard or explicit deferral |
| Emit analytics directly from Temporal workflow code | Workflow replay/task retry can duplicate side effects and violates deterministic workflow boundaries | Emit from a dedicated best-effort activity and keep alert evaluation independent of observability emission |
| Let timeliness emission failure fail the alert check | Observability outage becomes product alert outage | Catch/log/capture emission failures in the activity and treat workflow activity failure as best-effort |

## Temporal Implementation Pitfalls

See `references/temporal-slo-emission-pitfalls.md` for session-derived implementation notes covering replay-safe SLO emission, best-effort activity wiring, denominator rules, and test patterns.

## Baseline Pressure-Test Findings

Agents without this skill usually identify that success-rate is not timeliness, but drift toward generic formulas such as a 2-minute floor / 5-minute cap, 10% interval lag, and broad metric checklists. This skill pins the PostHog-specific 5%-with-60s/120s-clamp threshold, due-timestamp snapshot rule, denominator rule, and dashboard completeness gate.
