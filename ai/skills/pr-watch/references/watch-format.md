# Watch format (version 1)

One JSON file per watch in `~/.claude/state/pr-watch/watches/`. The check-in task appends to `~/.claude/state/pr-watch/history/<slug>.csv`.

The file is the whole contract between authoring and check-ins. Keep it free of anything that only works on one machine, apart from `notify` and the `tool` names, so the same shape can later be stored and run by a server.

The example below is invented. Take the shape from it, never the content.

```json
{
  "version": 1,
  "slug": "app-4182-export-dedupe",
  "status": "waiting_for_merge",
  "created_at": "2026-11-11T10:00:00Z",

  "subject": { "repo": "example/app", "prs": [4182], "public_repo": true },
  "change_type": "fix",
  "hypothesis": "Exports started within 5 minutes of an identical export nearly disappear.",
  "expected_size": null,

  "posthog": {
    "host": "https://us.posthog.com",
    "project_id": 1,
    "dashboard_url": "https://us.posthog.com/project/1/dashboard/123",
    "dashboard_created_by_watch": true,
    "dashboard_note": null
  },

  "live_signal": {
    "kind": "deploy",
    "rule": "first complete UTC day after the build containing the merge commit reached every production region",
    "query_id": null,
    "delay_hours": null
  },
  "live_at": null,

  "rollout": null,

  "comparison": "before_after",
  "baseline": { "from": "2026-10-28", "to": "2026-11-04", "note": "7 complete UTC days; `to` is exclusive" },

  "queries": {
    "q_exports": {
      "tool": "posthog:execute-sql",
      "language": "hogql",
      "text": "SELECT toDate(toTimeZone(created_at, 'UTC')) AS day, countIf(...) AS repeats_within_5m, uniqIf(...) AS people FROM ... WHERE toTimeZone(created_at, 'UTC') >= toDateTime('{from}', 'UTC') AND toTimeZone(created_at, 'UTC') < toDateTime('{to}', 'UTC') GROUP BY day ORDER BY day",
      "period_column": "day",
      "grain": "day"
    }
  },

  "metrics": [
    {
      "id": "m1",
      "name": "Exports within 5 minutes of an identical export, per day",
      "role": "primary",
      "source": "existing",
      "insight_url": null,
      "query_id": "q_exports",
      "value_column": "repeats_within_5m",
      "empty_means": "zero",
      "expected": "down",
      "baseline": { "mean": 412.6, "min": 371, "max": 455 },
      "gate": null
    },
    {
      "id": "g1",
      "name": "People who started an export, per day",
      "role": "guardrail",
      "source": "existing",
      "insight_url": null,
      "query_id": "q_exports",
      "value_column": "people",
      "empty_means": "no_data",
      "expected": "flat",
      "baseline": { "mean": 96.3, "min": 64, "max": 118 },
      "gate": {
        "op": ">=",
        "value": 69.3,
        "derived": "baseline mean 96.3 minus half the baseline range (118 - 64) / 2, against the 7-day mean because use has a weekly cycle; a halving would breach",
        "over": "7_day_mean",
        "min_sample": null,
        "sample_column": null
      }
    }
  ],

  "confounders": ["A pricing page change shipped inside the baseline window"],
  "not_measured": ["Refused exports: the change emits no event when it refuses one"],

  "cadence": { "every": "day", "quiet_unless_changed": true },
  "end": { "after_live_days": 7, "ended_at": null },

  "notify": { "slack_user_id": "U0000000000" },
  "last_checkin": null
}
```

## Queries

- `queries` holds each query once. Several metrics can read different columns of the same query; the check-in runs each query one time.
- `text` is stored with its placeholders, never with dates filled in. The check-in substitutes them and changes nothing else.
  - `{from}` and `{to}`: the window, UTC dates as `YYYY-MM-DD`, `from` inclusive, `to` exclusive. Required in every query.
  - `{baseline_from}` and `{baseline_to}`: optional, filled from `baseline.from` and `baseline.to`. For a query that has to compute the baseline gap itself (see Comparison).
- No literal date may appear in the text, and `now()` or `today()` may not either. Arithmetic on a placeholder is allowed, for example `toDate('{from}') - 1`. For a default in a window function use `toDateTime(0)`, not a date string.
- Before a query is stored it runs once with the baseline window substituted. A query that errors or times out in that run does not go in the watch.
- `language`: `hogql` or `sql` for the PostHog MCP and ClickHouse tools, `promql` for a Prometheus tool. For `promql`, `{from}` and `{to}` go in the tool's range parameters, and `text` holds the expression only.
- `tool`: `<server>:<tool>`, for example `posthog:execute-sql`, or the query tool of a ClickHouse or Prometheus server. Prefer a tool the unattended check-in can always reach. A query that needs a VPN or a login is allowed only when no other source has the data; say in `confounders` which metrics go dark when it is unreachable.
- All periods are complete UTC days. In HogQL wrap timestamps with `toTimeZone(..., 'UTC')`, because the project timezone is the default.
- A source that arrives late (an archive that lags a day) is named in `confounders` with its lag. The check-in reads only days the source has.

## Metrics

- `role`: `primary`, `guardrail`, or `context`. Only primaries and guardrails may carry a `gate`. Every guardrail has one.
- `source`: `existing` when the data was collected before this change, `new` when the diff adds it. A `new` metric has `baseline: null`.
- `empty_means`: `zero` when no rows is a real zero (an error count, a rare event), `no_data` when no rows means the query or the source is broken. This decides whether an empty result passes a gate or reports "cannot tell".
- `baseline`: the mean of the daily values over the baseline window, and the lowest and highest day. Check-ins use `min` and `max` to say whether a move is outside normal variation.
- `gate.value` is an absolute threshold. `gate.op` is the passing condition: the gate passes while `metric op value` holds, and breaches otherwise. `derived` says in words how it was set, so a reader can check it.
  - A primary that must fall carries a gate at its best baseline day, so an unchanged metric breaches.
  - `over: latest_day`: threshold from the worst baseline day plus half the baseline range.
  - `over: 7_day_mean`: threshold from the baseline mean plus half the baseline range. Use it for anything with a weekly cycle.
  - `min_sample` with `sample_column` makes the gate report "cannot tell" on thin data. Default: half the lowest baseline day of the sample column.
- A metric that covers one region says so in its `name`. The missing region goes in `not_measured`.

## Comparison

- `comparison: before_after`: values since `live_at` against `baseline`. Right for a change that reaches everyone at once.
- `comparison: exposed_vs_control`: each day, the exposed group against the control group on the same day. Right for a flag-gated change. The queries return the gap or the ratio directly as a column, and `baseline` holds that gap before any exposure, so a pre-existing difference between the groups is not credited to the change.
- When the groups are told apart by a marker that only exists after exposure, the query takes the groups from the window, computes their gap over `{baseline_from}` to `{baseline_to}` too, and returns each day as an index against it. `baseline.mean` is then 1 (or 0 for a difference) by construction, and `min` and `max` are the lowest and highest daily index inside the baseline window.

## Rollout

`null` for a change that is not behind a flag. Otherwise:

```json
"rollout": {
  "flag_key": "export-dedupe",
  "flag_id": 1234,
  "aggregation": "organization",
  "exposure_marker": "events carry properties.dedupe_reason only when the flag is on for the caller",
  "group_rule": "marker inside the window",
  "control_at_full": null,
  "stages": [
    { "at": "2026-11-04T18:44:00Z", "exposure": "one organization" },
    { "at": "2026-11-09T09:15:00Z", "exposure": "10%" },
    { "at": "2026-11-10T12:32:00Z", "exposure": "50%" }
  ],
  "read_from_stage": "50%",
  "final_stage": "50%"
}
```

- `stages` comes from the flag's activity log. The check-in appends new stages and reports a decrease as a rollback. It never changes the flag.
- `read_from_stage`: the first stage with enough exposure to read a result. `live_at` is the first complete UTC day at or past it, as a date (`YYYY-MM-DD`). When a fast ramp leaves no stage with a complete day, it is the final stage.
- `group_rule`: how the query splits exposed from control without a date: `hash cut-off`, `id list`, or `marker inside the window`. The rule is fixed at authoring. New stages are recorded in `stages` and never change a query.
- `control_at_full`: who stays unexposed with the flag at 100%, when the flagged code has its own condition (for example "teams over the volume limit"). `null` when 100% of the flag means everyone.
- `final_stage`: with `exposed_vs_control`, the last stage that still leaves a control group. That is `100%` when `control_at_full` is set, and the last partial stage otherwise. `end.after_live_days` counts from the first complete day at `final_stage` when it is reached, otherwise from `live_at`.
- With `control_at_full` null, a flag that reaches everyone ends the comparison: the check-in sends the closing summary on the days before that.

## Status and live signal

- `status`: `waiting_for_merge`, `waiting_for_live`, `live`, `done`, or `stopped`. A watch authored after the change is already live starts as `live` with `live_at` set. After creation, only the check-in task changes it.
- `live_signal.kind`: `deploy` (a deploy annotation or record whose build contains the merge commit), `flag_stage` (see Rollout), `new_code_event` (the first event only the new code emits), `metric_threshold`, or `merge_plus_delay`. `rule` states the inference in words.
- `subject.public_repo`: when true, nothing from a check-in is written back to the PR.
- `cadence.quiet_unless_changed`: when true, a check-in sends a message only on a status change, a new rollout stage, a gate result that differs from the last run, or the end of the watch.

## Not in version 1

Changing a flag. A watch reads a rollout; it does not drive one.
