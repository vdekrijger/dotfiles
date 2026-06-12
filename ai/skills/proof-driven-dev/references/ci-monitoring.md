# Phase 10: CI Monitoring + Bot Comment Handling

Detailed loop for monitoring CI and addressing bot comments after PR creation. The safety rules (verify-script rerun after every fix push, no force-push, 3-cycle escalation cap, never dismiss bot comments unaddressed) live in SKILL.md and always apply.

## CI Monitoring Loop

1. Poll CI status: `gh pr checks {PR_NUMBER} --watch`
2. If all checks pass and no bot comments need addressing: continue to Phase 11
3. If a check fails:
   a. Identify the failing check via `gh pr checks {PR_NUMBER}`, then fetch its logs
   b. Classify the failure:
      - **Auto-fixable** (lint error, type error, formatting, test failure in code you wrote): fix it, re-run the verify script to catch regressions, push
      - **Needs human input** (flaky test you didn't write, infra issue, CI config problem, permission issue): surface to the human with the failure details and ask for guidance
   c. After pushing fixes, return to step 1

## Bot Comment Handling

After CI passes (or in parallel), check for bot comments:
`gh api repos/{OWNER}/{REPO}/pulls/{PR_NUMBER}/comments`

For each bot comment:
1. **Actionable and auto-fixable** (linter suggestions, security scanner findings in your code, coverage threshold warnings): fix, push, re-poll
2. **Actionable but needs judgment** (dependency upgrade suggestion, architectural concern from a static analysis bot): surface to the human with context and your recommendation
3. **Informational only** (deploy preview links, changelog generation, size reports): note and move on

## Escalation Prompt for Human Input

```
[proof-driven-dev] CI/bot comment needs your input:

  Check: {CHECK_NAME}
  Status: {FAILING / BOT_COMMENT}
  Details: {SUMMARY_OF_ISSUE}

  My assessment: {YOUR_ANALYSIS}
  Recommended action: {WHAT_YOU_THINK_SHOULD_HAPPEN}

  What would you like me to do?
```
