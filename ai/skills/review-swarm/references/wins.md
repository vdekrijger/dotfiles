# Review-swarm wins log

Append-only record of "great catch" findings — confirmed real by the user during Stage 5 of /review-swarm.
Format mirrors `calibration.md`. Read by Stage 2 to feed each reviewer its past wins.

## 2026-04-28 — posthog — posthog-pr56706-20260428-124136.html
PR #56706 (mcp-alert-slack-recipe). v1 review-swarm pass on a YAML-only PR documenting an alert→Slack MCP recipe and enabling integrations-channels-retrieve. The convergent HIGH finding caught a real auth bug that would have shipped the feature non-functional.

- Finding #1 (qa-team/security, HIGH): The `channels` action is not in `IntegrationViewSet.scope_object_read_actions`, so `_get_required_scopes` returns None for it and `APIScopePermission` denies every Personal API Key / OAuth caller with "This action does not support Personal API Key access". The MCP tool YAML correctly declared `integration:read`, but the backend would 403 every MCP caller — primary auth path for this product. The newly-enabled tool would have been non-functional.
  Location: posthog/api/integration.py:442
  Marked WIN. Note: The original headline bug. Author had enabled the tool in YAML but missed the backend scope-action mapping. Fix was a one-line addition to scope_object_read_actions plus a corresponding queryset change. Pattern to keep raising: when a YAML enables an MCP tool, verify both `scope_object_read_actions` AND `safely_get_queryset` cover the path.

- Finding #1 (qa-team/compatibility, HIGH): Same scope gap — YAML declares integration:read but backend never grants read-scope access to the channels action via API keys. Convergent with security lane.
  Location: posthog/api/integration.py:442
  Marked WIN. Note: Compatibility lane caught the YAML <-> backend contract drift independently of security. Worth keeping for future PRs that flip MCP enabled flags without checking the corresponding backend permission wiring.

## 2026-04-28 — posthog — posthog-pr56706-20260428-132146.html
PR #56706 (mcp-alert-slack-recipe). v2 review-swarm pass after the v1 scope fix landed. The swarm went deeper and found three new HIGHs that had been masked by the bigger v1 bug, plus several MEDIUMs that materially improved the implementation.

- Finding #1 (vasco, HIGH): The channels-action queryset filtered `kind__in=["github", "slack"]`. Two issues: (a) GitHub passing through resulted in a 500 from `SlackIntegration.__init__`'s bare Exception, not a clean 404. (b) `SlackIntegration` actually accepts both `slack` and `slack-posthog-code`, so the second variant got silent 404. Right shape was `kind__in=["slack", "slack-posthog-code"]` plus a defensive kind guard.
  Location: posthog/api/integration.py:488
  Marked WIN. Note: Vasco lane caught the queryset still allowing the wrong kinds even after a "narrowed" fix. The kind variants (slack vs slack-posthog-code) are easy to miss — they exist because of OAuth redirect URI plumbing in posthog/models/integration.py:1041. Pattern: when narrowing a kind allowlist, check what the integration class's __init__ actually accepts.

- Finding #1 (code-reviewer, HIGH): Same kind handling bug — queryset omitted `slack-posthog-code` AND let github through to a 500 path from SlackIntegration's bare Exception. Convergent with vasco and qa-team/security.
  Location: posthog/api/integration.py:488
  Marked WIN. Note: Code-reviewer caught the slack-posthog-code variant gap by reading SlackIntegration.__init__ and noting the kind allowlist there didn't match the queryset. Worth keeping for any "slack-only" filter — the kind list lives in two places and tends to drift.

- Finding #1 (qa-team/security, HIGH): Same bug — channels action passes instance to SlackIntegration without first checking instance.kind, so a github id resolves through the queryset and hits SlackIntegration's bare Exception which becomes a 500, not a 400. Convergent.
  Location: posthog/api/integration.py:526
  Marked WIN. Note: Security lane independently caught that the kind guard was missing from the action itself. The queryset filter is one layer; the action's own defensive check is the actual safety net for future drift.

- Finding #2 (sre, HIGH): The recipe instructs agents to call cdp-functions-list and check filters before creating, to avoid duplicates on retry. But cdp-functions-list MCP response (cdp_functions.yaml `include` list) does NOT include filters — and the underlying viewset uses HogFunctionMinimalSerializer for list, which has filters in the model serializer but the MCP layer strips it out. So the dedupe lookup is a fiction; agents would N+1 retrieve or just silently skip the check. Idempotency story collapses under retry.
  Location: products/alerts/mcp/tools.yaml:144
  Marked WIN. Note: Excellent SRE catch — looked all the way through the MCP layer's response include filtering, not just the underlying serializer. Pattern: when a recipe relies on a list-call returning specific fields, verify the MCP `response.include` actually exposes them. The minimal-serializer-plus-MCP-filter combination is a standard pattern that produces this gap.

- Finding #4 (qa-team/reliability, MEDIUM): Even if filters were exposed, cdp-functions-list paginates at PAGE_SIZE=100 (settings/web.py:351). A project with 100+ internal_destination functions silently misses matches on page 2+ → duplicate Slack notifications. Recipe should specify limit=1000 or paginate.
  Location: products/alerts/mcp/tools.yaml:38
  Marked WIN. Note: Reliability lane caught a downstream-of-the-HIGH issue — even after the filters fix, default pagination would still cause silent miss. Pattern: agent recipes that scan list endpoints need explicit pagination guidance.

- Finding #7 (vasco, MEDIUM): Description claimed "calling this with a non-Slack integration returns a 400" — actually returned 500 (unhandled bare Exception from SlackIntegration). Convergent with code-reviewer and qa-team/security.
  Location: products/integrations/mcp/tools.yaml:203
  Marked WIN. Note: vasco lane caught the documentation/behavior mismatch. Pattern: when a description states a specific HTTP error code, trace the actual code path to verify.

- Finding #9 (qa-team/compatibility, MEDIUM): Recipe says use channel `id` from integrations-channels-retrieve (e.g. C0123ABC) as channel.value. But existing test fixtures use "#general" and the slack template input description says "Select the channel to post to (e.g. #general)". Slack API accepts both, but the recipe-vs-tests-vs-template inconsistency would confuse agents debugging failures.
  Location: products/alerts/mcp/tools.yaml:34
  Marked WIN. Note: Compatibility lane caught the format inconsistency across three sites (recipe, tests, template description). Pattern: when adding a recipe that names a value format, audit the existing canonical references for that field.

- Finding #3 (xp, HIGH): Slack/webhook recipe duplicated near-verbatim across alert-create and cdp-functions-create. Five magic strings (internal_destination, template-slack, template-webhook, $insight_alert_firing, alert_id) now load-bearing across yaml + product code with no drift detector. Rule 3 violation.
  Location: products/alerts/mcp/tools.yaml:30
  Marked WIN. Note: XP lane was right that the duplication-for-discoverability tradeoff was worse than the duplication. Consolidating to one canonical recipe + short pointers from the other tools made the descriptions cleaner AND closed the drift risk. Pattern: agent-prompt discoverability claims need to be balanced against magic-string drift across yaml + product code.

## 2026-05-29 — posthog — pr-feedback-miner (14-day scan: PRs #53837–#60399)

Mined 9 merged PRs for human review feedback. Filtered out self-reviews and bot comments. Key patterns below.

- Finding (vasco, HIGH): Comment discipline — 5+ instances across PRs #59625, #59624 where the user had to tell the agent to remove or simplify verbose comments. Pattern: "simplify this comment", "remove this comment", "no need for this verbosity", "focus on the WHY", "it's implicit". The agent writes multi-line doc-blocks and commit-message-style inline comments on functions whose purpose is already clear from the code.
  Location: PR #59625 (AI credit budget gate), PR #59624 (freemium subscriptions)
  Marked WIN. Note: This is the single highest-frequency pattern — the user corrects it in nearly every agent-authored PR. vasco-reviewer priority #14 (comment discipline) added to catch this. The rule: a comment is only worth keeping if it explains what the code cannot express.

- Finding (vasco, MEDIUM): Missing actionable links from error states. PR #59625 added an AI credit budget gate that silences summaries when over budget. Human reviewer flagged that the error message told users what happened but didn't link them to Billing to fix it. Slack and email reports now include a link. Pattern: when an error state has a resolution path (settings page, billing page, docs), include the link.
  Location: PR #59625 (MattPua review comment)
  Marked WIN. Note: vasco-reviewer priority #15 (UX: actionable error recovery) added to catch this proactively.

- Finding (vasco, LOW): Test type appropriateness — human reviewer questioned whether a Playwright (full-browser) test was justified vs a simpler component test. Agent had added Playwright test + screenshots as proof-of-work to a feature PR; reviewer correctly identified it as overkill for the behavior being tested.
  Location: PR #59624 (MattPua review comment: "non blocker: is this a test thats worth having as playwright test?")
  Marked WIN. Note: vasco-reviewer priority #3 (meaningful assertions) already covers this — the Playwright test would have passed with an empty implementation of the underlying logic. The win is validating that the existing rule catches this pattern.

- Finding (vasco, MEDIUM): Scope discipline — agent regenerated `schema.json` / `schema.py` alongside a comment-only change. User flagged it as unnecessary diff noise.
  Location: PR #59624
  Marked WIN. Note: vasco-reviewer priority #4 (scope discipline) covers this — accidental regenerated files in a PR. Keep raising it.

