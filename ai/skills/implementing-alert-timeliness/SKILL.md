---
name: implementing-alert-timeliness
description: Use when implementing or reviewing PostHog alert-check timeliness, scheduler lateness, due-work SLOs, alert backlog dashboards, Temporal SLO emission, or alert-check observability.
---

# Implementing Alert Timeliness

Alert-check timeliness is a separate SLO from alert execution: a check that starts too late is an SLO failure even if the query later succeeds. Proof target: operators can tell whether checks started close to their scheduled due time.

**Mode selection** — full pipeline when the work adds `SloOperation`/alert timing events, changes the alert scheduling/evaluation flow, or adds dashboard/Terraform/query panels; review mode when assessing an already-written diff or answering conceptual SLO threshold questions.

## Full Pipeline

1. **Discover current state.** Read the alert scheduling and evaluation paths before editing. Anchors: `posthog/temporal/alerts/schedule.py`, `posthog/temporal/alerts/activities.py::retrieve_due_alerts`, `posthog/tasks/alerts/utils.py::add_alert_check`, `posthog/slo/`. If PostHog MCP is available, query live alert telemetry before choosing thresholds or dashboard language.

2. **Define the SLI contract.** Eligible: a scheduled alert check with a non-null due timestamp. Good: starts within the threshold of the original due timestamp. Bad: starts after threshold, times out before start, skipped due to backlog, or missing from due-work accounting. Exclude initial/no-schedule checks (`next_check_at is None`) from the denominator — do not emit success for them.

3. **Choose the threshold.**

   ```text
   allowed_lag = clamp(interval_seconds * 0.05, min=60s, max=120s)
   ```

   1-minute alerts get one scheduler tick of grace; 15-minute alerts stay at the 60s floor; hourly and longer cap at 120s so long intervals can't hide backlog. 10% is too lenient for the agreed PostHog SLO unless product/SRE explicitly revises the target; avoid 5-minute caps unless the SLO intentionally tolerates multi-minute lateness.

4. **Write criteria before code.**
   - REQ-TIME-1: Distinct `SloOperation` / event name from execution success.
   - REQ-TIME-2: Original due timestamp snapshotted before `add_alert_check` or any path mutates `next_check_at`.
   - REQ-TIME-3: Late-but-successful checks emit timeliness failure and execution success.
   - REQ-TIME-4: No-due initial checks excluded, not counted as successful.
   - REQ-TIME-5: Threshold covers 1m, 15m, hourly, daily, weekly, monthly intervals without `relativedelta` ambiguity.
   - REQ-TIME-6: Dashboard/Terraform/query visibility included or explicitly deferred in the plan/PR.

5. **Implement with TDD.** Failing tests first, in order: threshold calculation; due-timestamp snapshotting before mutation; late success classified as timeliness failure; no-due checks not inflating the denominator. Then the smallest code to pass. When asserting SLO payload fields that depend on deployment config (e.g. `region` from `get_instance_region()`), patch the helper (`@patch("posthog.temporal.alerts.activities.get_instance_region", return_value="US")`) — CI may legitimately return `None`, making a valid test flaky.

6. **Wire observability.** Suggested event fields: `alert_id`, `insight_id`, `team_id`, `calculation_interval`, `scheduled_due_at`, `actual_check_start_at`, `evaluation_lag_ms`, `timeliness_threshold_ms`, `is_late`. Keep high-cardinality labels out of metrics — event properties are safer for exploratory HogQL. Keep execution SLO fields/events separate from timeliness ones. In Temporal, emit timeliness SLOs from a dedicated best-effort activity, never directly from workflow code — workflow-side analytics can duplicate on replay/task retry and must not block alert evaluation. See `references/temporal-slo-emission-pitfalls.md`.

7. **Prove with live-style queries.** Dashboard: on-time %, late %, p50/p90/p99 lag, current backlog, split by interval/source where useful. PostHog MCP/HogQL: discover schema first, include `LIMIT 100`, never print secrets. Useful existing telemetry: `alert check backlog`, `poc_alerting_pipeline_health`, `poc_alerting_exception_run_summary`, `poc_alerting_ticket_run_summary`.

8. **Review hardening.** Run SRE review on the diff, explicitly asking: "Could this query succeed late and still look green?" Run the normal suite plus targeted alert/SLO tests. If dashboard/Terraform is deferred, the PR must say what follow-up makes the SLO visible.

## Review Mode Checklist

Flag the diff if any answer is "no":

1. Is alert-check timeliness separate from alert-check execution success?
2. Is the scheduled due timestamp captured before it can be mutated?
3. Does too-late count as failure even when evaluation succeeds?
4. Are initial/no-due checks excluded from the denominator?
5. Does the threshold avoid hiding long-interval backlog?
6. Is there visible dashboard/SLO wiring, or an explicit deferral?
7. Can operators query current split/backlog without reading application logs?

## Current Query Pattern

With live data, compute both backlog ("are checks waiting?") and duration split ("is the pipeline slow?"). Neither replaces the dedicated SLO; both ground the rollout.

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

| Failure | Why wrong | Fix |
|---|---|---|
| Reuse execution success as timeliness | Late successes look healthy | Separate timeliness operation/outcome |
| Measure only completion | Conflates queue delay with evaluation duration | Capture due, start, and completion separately |
| Read `next_check_at` after evaluation | `add_alert_check` may mutate it | Snapshot original due time first |
| Count first/no-due checks as success | Inflates denominator | Exclude or track separately |
| Threshold is 10% or percentage-only | Daily/monthly checks hide hours of lateness | 5% with 60s floor, 120s cap |
| Instrumentation without dashboard | Operators can't use it | Terraform/dashboard or explicit deferral |
| Emit analytics from Temporal workflow code | Replay/retry duplicates side effects; breaks determinism | Dedicated best-effort activity |
| Timeliness emission failure fails the check | Observability outage becomes alert outage | Catch/log emission failures; activity is best-effort |

## Temporal Implementation Pitfalls

See `references/temporal-slo-emission-pitfalls.md` for replay-safe SLO emission, best-effort activity wiring, denominator rules, and test patterns.

Agents without this skill drift to generic formulas (2-minute floor / 5-minute cap, 10% lag, broad metric checklists); this skill pins the PostHog-specific 5%-with-60s/120s-clamp threshold, due-timestamp snapshot rule, denominator rule, and dashboard completeness gate.
