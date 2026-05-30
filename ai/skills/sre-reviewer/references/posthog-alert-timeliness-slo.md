# PostHog Alert Timeliness SLO Notes

Use these notes when reviewing or designing PostHog alert-check observability, especially changes under `posthog/temporal/alerts/`, `posthog/tasks/alerts/`, `posthog/slo/`, or Terraform dashboard/SLO config.

## Current scheduling facts

- Due alert checks are scheduled by `posthog/temporal/alerts/schedule.py`.
- The schedule id is `schedule-due-alert-checks-schedule`.
- The Temporal schedule currently runs every minute with `cron_expressions=["*/1 * * * *"]`.
- The schedule uses `ScheduleOverlapPolicy.ALLOW_ALL` and a workflow execution timeout of 10 minutes.
- Due alerts are selected in `posthog/temporal/alerts/activities.py::retrieve_due_alerts` with `next_check_at__lte=now` or `next_check_at__isnull=True`.
- Alert evaluation mutates `next_check_at` through `posthog/tasks/alerts/utils.py::add_alert_check`, so any timeliness measurement must snapshot the due timestamp before evaluation/add-alert-check updates it.

## Preferred SLO shape

Track alert-check timeliness separately from alert-check execution:

- `ALERT_CHECK_TIMELINESS`: did the worker start close enough to the scheduled due time?
- `ALERT_CHECK`: did the evaluation itself succeed/fail?

Do not overload execution success with timeliness. A query can succeed after starting too late; that should still be a timeliness SLO failure.

## Threshold model discussed

Preferred threshold formula:

```text
allowed_lag = clamp(interval_seconds * 0.05, min=60s, max=120s)
```

Rationale:

- Future 1-minute alerts get a 60s threshold, matching the 1-minute scheduler cadence.
- 15-minute alerts stay at the 60s floor, allowing one scheduler tick of slack without tolerating multi-minute delay.
- Hourly/daily/weekly/monthly alerts are capped at 120s so long intervals do not hide backlog.

10% with the same 60s floor / 120s cap is too lenient for the agreed SLO unless product/SRE explicitly revises the target. A fixed 60s threshold is simpler but may be too tight for hourly alerts under normal Temporal dispatch jitter.

## Event properties to expect

For timeliness SLO events, useful properties include:

- `alert_id`
- `insight_id`
- `team_id`
- `calculation_interval`
- `scheduled_due_at`
- `actual_check_start_at`
- `evaluation_lag_ms`
- `timeliness_threshold_ms`
- `is_late`

For `next_check_at is None`, prefer not emitting the timeliness SLO because there is no scheduled due timestamp. Emitting success for no-due initial checks pollutes the denominator.

## Review checklist

When reviewing a PostHog alert timeliness SLO change, check that:

1. A distinct `SloOperation` is added for timeliness, not just reusing evaluation success.
2. The original `next_check_at`/due timestamp is snapshotted before `add_alert_check` or any path that mutates it.
3. Too-late checks produce `SloOutcome.FAILURE` even if evaluation later succeeds.
4. Initial/no-schedule checks (`next_check_at is None`) do not inflate the timeliness success denominator.
5. The threshold function handles future minute-level intervals and long intervals without `relativedelta` ambiguity for months.
6. Terraform/dashboard wiring is included or explicitly deferred, because invisible SLO instrumentation is incomplete.
