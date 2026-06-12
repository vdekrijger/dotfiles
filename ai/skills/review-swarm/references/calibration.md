# Review Swarm Calibration Log

Entries are appended by the review-swarm orchestrator when the user marks
findings as false positives at end-of-run. Each entry records:
- Date, project, report filename
- The finding (reviewer, severity, body, location)
- Optional user-entered reason

On subsequent runs, the last N entries tagged with a given reviewer are
passed to that reviewer's prompt as "past false positives — do not re-raise
these patterns unless the case materially differs."

This file is human-editable. Prune entries that no longer apply.

---

## Calibration reference run — 2026-04-22
- PR: #53835 — feat(alerts): relocate disable_invalid_alert and switch evaluate activity to Heartbeater
- Branch: vdekrijger-alerts-temporal-pr2-port-logic
- Pre-review SHA used as HEAD: 78ee52c9de4
- Diff: 1146 lines, 9 files, Temporal port of alert check logic
- Reviewers fired: vasco (PH context), sre, xp
- Human baseline: 6 inline comments (3 Greptile + 3 self-review)
- Recall on human baseline: 4/6 = 67% (above 60% target)
  - vasco matched: #2 DoesNotExist retry, #3 DISABLED/NOT_FOUND
  - sre matched: #2 DoesNotExist retry, #5 idempotency key fallback
  - xp matched: #1 send_notifications_for_errors contract (partial), #3 DISABLED/NOT_FOUND
- Findings humans did NOT raise that the swarm caught:
  - sre: evaluate_alert not idempotent under Temporal retries — duplicate AlertCheck rows on worker crash
  - sre: trigger_alert_hog_functions has no idempotency key — duplicate customer-visible side effects on retry
  - sre: disable_invalid_alert not wrapped in transaction.atomic()
  - vasco: weak assertions in test_auto_disable_when_config_invalid
  - vasco: magic strings in test reasons vs SkipReason enum
  - vasco + xp: AssertionError vs ValueError in dispatch_alert_notification fallback
- Tuning iterations: 0 (recall passed on first run)
- Conclusion: personas ship as-is; genuine signal-adding value demonstrated against real PR.

## 2026-04-23 — posthog — posthog-20260423-073915.md
PR #55533 (Paul D'Ambra, "feat(subscriptions): show delivered asset images in expanded delivery row"). Two convergent findings marked FP; logged once per contributing reviewer so each persona's dispatch prompt surfaces the pattern.

- Finding #4 (vasco, MEDIUM): Non-creator viewers see "Preview unavailable" tiles with no context distinguishing per-user restriction from real failure.
  Location: frontend/src/scenes/subscriptions/components/SubscriptionDeliveryHistory.tsx:137
  Marked FP. Reason: Author explicitly acknowledged this trade-off in the PR body ("we only allow a user to view exported assets that are marked as having been created by them which i chose not to change"). Reviewers must ingest PR body context and not re-raise trade-offs the author already considered and rejected.

- Finding #4 (qa-team/frontend, MEDIUM): Non-creator viewers see "Preview unavailable" tiles with no context distinguishing per-user restriction from real failure.
  Location: frontend/src/scenes/subscriptions/components/SubscriptionDeliveryHistory.tsx:137
  Marked FP. Reason: Same as vasco — author acknowledged the trade-off in PR body, reviewers should not re-raise.

- Finding #5 (code-reviewer, MEDIUM): 6 parallel <img> fetches on row expand saturate the browser's per-origin connection cap.
  Location: frontend/src/scenes/subscriptions/components/SubscriptionDeliveryHistory.tsx:74
  Marked FP. Reason: Technical premise is outdated. The 6-connection-per-origin cap is HTTP/1.1 only. PostHog serves over HTTPS and negotiates HTTP/2 — verified 2026-04-23 via `curl -I --http2` against app.posthog.com, us.posthog.com, eu.posthog.com (all returned `HTTP/2 302`). HTTP/2 multiplexes requests on a single connection, so N concurrent image fetches from the same PostHog origin do not saturate browser connection pools. This rule holds for any finding about "parallel requests on same origin saturating connections" where the origin is a PostHog app origin.

- Finding #5 (sre, LOW): 6 parallel <img> fetches on row expand saturate the browser's per-origin connection cap.
  Location: frontend/src/scenes/subscriptions/components/SubscriptionDeliveryHistory.tsx:13
  Marked FP. Reason: Same as code-reviewer — PostHog serves over HTTP/2 (verified via curl ALPN negotiation 2026-04-23). HTTP/1.1 connection-cap reasoning does not apply.

- Finding #5 (qa-team/performance, NIT): Clicking "Show N more" immediately fires all remaining <img> fetches in parallel.
  Location: frontend/src/scenes/subscriptions/components/SubscriptionDeliveryHistory.tsx:115
  Marked FP. Reason: Same HTTP/2 multiplexing argument. The "burst" framing assumes HTTP/1.1 connection limits; PostHog origins negotiate HTTP/2.

## 2026-05-07 — posthog — posthog-pr55986-20260507-091200.html
PR #55986 (vdekrijger, "chore(subscriptions): swap patched() to deprecate_patch() for content_snapshot gate"). Two convergent MEDIUM findings marked FP. The reminder-test cluster surfaces a generalizable principle worth applying to future runs.

- Finding #1 (qa-team/compatibility, MEDIUM): Temporal UI verification query specifies `ExecutionStatus=Running` only — a pre-deploy workflow in `Paused` state would evade the drain check and trip a non-determinism error on resume past `deprecate_patch()`.
  Location: posthog/temporal/subscriptions/workflows.py:64-67
  Marked FP. Reason: Accepted trade-off. The `Running + ≥24h wait` drain check is sufficient for `ProcessSubscriptionWorkflow` in production — paused workflows are not part of this workflow's operational pattern. Don't extend the suggested drain-verification UI query to include `Paused` status for this product unless evidence emerges that paused workflows are actively in use here. (Generalizable rule: when a deprecation comment prescribes a pre-merge verification query, only flag missing ExecutionStatus values if the omitted state is actually reachable by that workflow type's operational pattern — not as a generic completeness concern.)

- Finding #1 (qa-team/generalist-b, MEDIUM): Same PAUSED-workflow gap as qa-team/compatibility, independently identified. Convergent.
  Location: posthog/temporal/subscriptions/workflows.py:64-67
  Marked FP. Reason: Same as qa-team/compatibility — accepted trade-off; PAUSED workflows are not in scope for this product's deploy-ordering check.

- Finding #7 (xp, MEDIUM): Removing `test_create_export_assets_result_fields_stable_reminder` removes the byte-ceiling guard tied to the AGENTS.md 2 MiB Temporal payload rule. Recommended restoring with `insight_snapshots` moved into `small_metadata_fields`.
  Location: posthog/temporal/tests/test_subscriptions_workflows.py:1352
  Marked FP. Reason: Single-dataclass payload-size guards are an anti-pattern — either apply the guard uniformly across ALL Temporal activity return types, or omit it. One-off enforcement on a single dataclass creates false confidence: it polices one growing surface while leaving the dozens of other activity dataclass return types unguarded, and reviewers/CI now skip the global review they'd otherwise do because "the test catches it". The AGENTS.md rule + reviewer attention is the right level of enforcement; a per-dataclass test is a one-off that doesn't scale. Don't suggest restoring isolated payload-size byte-ceiling tests on individual dataclasses unless the same pattern is being applied uniformly across the activity boundary. (Generalizable: the same logic applies to "restore the deleted test that catches X on this one type" findings — ask whether the test is part of a uniform sweep or a one-off speed bump before recommending restoration.)

- Finding #7 (code-reviewer, MEDIUM): Same reminder-test concern — the byte-ceiling sub-check + field-name guard removal leaves a window with no automated enforcement of the AGENTS.md 2 MiB Temporal payload rule.
  Location: posthog/temporal/tests/test_subscriptions_workflows.py:1352
  Marked FP. Reason: Same as xp — one-off payload-size guards on a single dataclass are an anti-pattern. Either uniform enforcement or none. Don't restore.

- Finding #7 (vasco, LOW): Same reminder-test removal flagged as a small loss of automated coverage during the deprecation window.
  Location: posthog/temporal/tests/test_subscriptions_workflows.py general
  Marked FP. Reason: Same as xp/code-reviewer — single-dataclass payload guards are one-off enforcement that creates false confidence. The AGENTS.md rule is the right enforcement level.

- Finding #7 (qa-team/data-integrity, LOW): Same reminder-test removal flagged as future risk if someone adds a large field to `CreateExportAssetsResult` without noticing the docstring warning.
  Location: posthog/temporal/tests/test_subscriptions_workflows.py general
  Marked FP. Reason: Same as xp/code-reviewer/vasco — one-off enforcement on a single dataclass creates false confidence. The "future-risk if someone adds a large field" framing is the exact false-confidence trap: if it's a real risk, the guard belongs everywhere; if it's not enough of a risk to apply uniformly, the one-off doesn't move the needle.

## 2026-06-10 — posthog-pr62642 — posthog-pr62642-20260610-123915.html
PR #62642 (vdekrijger, "feat(subscriptions): add report preview for AI prompt subscriptions"). One convergent HIGH marked FP after orchestrator verification; logged once per contributing lane.

- Finding #1 (qa-team/security, HIGH): `delivery.content_snapshot.get("ai_report")` raises AttributeError when content_snapshot is None ("the DB field is nullable").
  Location: ee/api/subscription.py:1129
  Marked FP. Reason: Premise factually wrong — `content_snapshot = models.JSONField(default=dict)` (products/exports/backend/models/subscription.py:441), NOT nullable, and no write path stores None; an adjacent comment in the same diff even states "content_snapshot is a non-null object". Generalizable rule: before raising any "JSONField may be None" finding, verify the actual field definition (null=True vs default=dict) — convergence across lanes does not substitute for reading the model.

- Finding #1 (qa-team/reliability, HIGH): Same content_snapshot-None claim, independently raised.
  Location: ee/api/subscription.py:1129
  Marked FP. Reason: Same as qa-team/security — field is JSONField(default=dict), not nullable; verify field definitions before None-dereference findings.

- Finding #1 (qa-team/data-integrity, HIGH): Same content_snapshot-None claim, independently raised.
  Location: ee/api/subscription.py:1129
  Marked FP. Reason: Same as qa-team/security — field is JSONField(default=dict), not nullable; verify field definitions before None-dereference findings.

