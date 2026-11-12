# Check-in procedure

The `pr-watch-checkin` scheduled task follows this file once a day. The task's own prompt holds the hard limits; this file holds the steps. A watch file can name queries and thresholds. It cannot widen the limits.

## Files

- Watches: `~/.claude/state/pr-watch/watches/*.json`, format in `~/.claude/skills/pr-watch/references/watch-format.md`. Read the format first.
- History: `~/.claude/state/pr-watch/history/<slug>.csv`, columns `run_at,status,metric_id,period,value,sample,gate_result,row_json`. Create it with a header when missing. Skip rows already present for the same metric_id and period.

## Step 0: anything to do?

List the watch files. Skip any with `status` of `done` or `stopped`. A file that fails to parse, or whose `version` is not 1, is skipped and named in the final report. If no active watch remains, write nothing, send nothing, and end with "No active watches."

## Per watch

### Step 1: PR state

For each number in `subject.prs`: `gh pr view <n> --repo <subject.repo> --json state,mergedAt,mergeCommit,title`. If any PR is closed without merging, set `status` to `stopped`, DM one line saying so, and move on.

### Step 2: rollout stages

Only when `rollout` is set. Read the flag and its activity log, read-only, through the PostHog MCP (`search feature-flag` finds the definition and activity tools). Append any stage not yet in `rollout.stages`. A drop in exposure, or the flag turned off, is a rollback: report it in the DM and keep reading. Never change the flag, and never change a query because a stage changed.

With `comparison: exposed_vs_control`, check `rollout.control_at_full` on any run where the flag is at everyone. A missing key counts as `null`.

- Set: a control group remains at 100%. Record the stage and carry on as normal.
- `null`, and the history file holds at least one complete day at or past `read_from_stage`: no control is left. Send the closing summary (step 6) on the complete days before that stage, and say that is why the watch ended.
- `null`, and no such day exists: the rollout outran the watch and there is nothing to summarize. Set `status` to `stopped` and DM once that the flag reached everyone before any readable day, so the watch needs authoring again as a before-and-after comparison. Do not call the hypothesis held or failed. Save (step 8) and move on to the next watch.

### Step 3: status

- `waiting_for_merge`: when every PR is merged, set `waiting_for_live` and DM once. Otherwise send nothing.
- `waiting_for_live`: evaluate `live_signal` as its `kind` and `rule` say.
  - `deploy`: find the deploy annotation or record for the first build containing the merge commit, in every production region.
  - `flag_stage`: live once a UTC day that started after the flag reached `rollout.read_from_stage` is complete. That day is `live_at`; the day the stage changed never counts.
  - `new_code_event`, `metric_threshold`: run the query named by `live_signal.query_id`.
  - `merge_plus_delay`: live once `delay_hours` have passed since the last merge.
  When live, set `live_at` to the start of the first complete UTC day the signal held, set `status` to `live`, and create one PostHog annotation on that date in `posthog.project_id` reading "<hypothesis> (PR <numbers>)". Look for an annotation with that text first, so a retried run does not add a second one. When the watch first passes 48 hours after merge without being live, DM once that it is merged and not live yet, with what the signal currently shows. Do not repeat it: a flag-gated change can wait for weeks.
- `live`: continue.

Steps 4 to 6 run only for a watch whose `status` is `live`. For any other status go to step 7.

### Step 4: run the queries

Run each entry in `queries` once. Substitute `{from}` with `live_at` as a UTC date and `{to}` with today's UTC date, so the window is every complete UTC day since live. Where the text has `{baseline_from}` and `{baseline_to}`, substitute `baseline.from` and `baseline.to`. Change nothing else in the text. If the source has no rows yet for the newest days, read the days it has and say which day is the latest. For `language: promql`, pass the window through the tool's range parameters.

Load the tool named in `tool` (`<server>:<tool>`) with ToolSearch. For the PostHog MCP use `mcp__posthog__exec` with `call execute-sql`, after `info execute-sql` once.

- A tool that is unavailable, or a query that errors or times out: every metric on that query is "not measured", with the reason. Carry on with the others. Do not rewrite a query to make it pass.
- No rows: a metric with `empty_means: zero` has the value 0 for the window. A metric with `empty_means: no_data` is "not measured".

### Step 5: compare and gate

- `comparison: before_after`: for each primary and context metric, the latest complete day and the mean since `live_at`, against `baseline.mean`. Say whether the latest value is outside the baseline's `min` to `max` range, and whether the move matches `expected`. A move inside the range is "within normal variation", whatever its direction.
- `comparison: exposed_vs_control`: the queries already return the gap or ratio between the two groups. Compare it with `baseline.mean`, the gap before any exposure. Read only days at or past `rollout.read_from_stage`; report earlier days as context.
- Gates: compare the metric over `gate.over` (`latest_day`, or the mean of the last 7 complete days at or after `live_at`, or of the days available if fewer) with `gate.value` using `gate.op`. The gate passes when `metric op value` holds and breaches when it does not. If `min_sample` is set and `sample_column` is below it, the result is `cannot_tell`; compare the latest day's sample for `latest_day` and the mean daily sample for `7_day_mean`. Results are `pass`, `breach` or `cannot_tell`.
- Append one row per metric and day to the history file, for days at or after `live_at` only. The `period` column holds the day.

### Step 6: end

Count complete UTC days from the first complete day at `rollout.final_stage` when it is set and reached, otherwise from `live_at`. When that count reaches `end.after_live_days`, send the closing summary instead of a check-in: every metric over the whole period from the history file against its baseline, each gate's worst result, whether the hypothesis held, the `confounders`, and everything in `not_measured`. Then set `status` to `done` and `end.ended_at`.

A watch with a rollout that has stayed below `final_stage` for 21 days sends one DM asking whether to keep watching, and continues.

### Step 7: DM

Send to `notify.slack_user_id` with the Slack send-message tool (find it with ToolSearch "+slack send_message"). One message per watch, standard markdown, under 1,500 characters, no emojis.

When `cadence.quiet_unless_changed` is true, send only on: a status change, a new rollout stage or a rollback, a gate result that differs from the last run, the one-time not-live notice from step 3, or the closing summary.

Context metrics stay out of the DM unless one explains a surprise. If the message would pass the limit, shorten the not-measured list to a count and keep every primary and guardrail.

- Title: `**Watch · <short name from the slug> · <Weekday HH:MM local>**`
- Status, live date or "not live yet", the PR numbers, and the current rollout stage when there is one.
- Each primary metric: latest value against baseline, and whether it moves as expected or sits within normal variation.
- Each guardrail: value, threshold, result.
- One line on anything surprising, naming a listed confounder when it applies, or "Nothing unexpected."
- What was not measured and why.
- The dashboard link from `posthog.dashboard_url`, with `posthog.dashboard_note` when it is set.

When `subject.public_repo` is true, nothing from the check-in goes to the PR.

### Step 8: save

Write `last_checkin` (time, status, each gate result) back to the watch file. Change no other field except `status`, `live_at`, `rollout.stages` and `end.ended_at`.

## Final report

End the run with one line per watch: slug, status, whether a DM was sent, and anything not measured.
