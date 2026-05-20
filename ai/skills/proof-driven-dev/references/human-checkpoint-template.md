# Human Checkpoint Template

Template for presenting verification results to the human for review.
The orchestrator fills in the placeholders and presents this as a
structured message.

---

## What Was Built

{FEATURE_SUMMARY}

## Verification Status

{VERIFICATION_SUMMARY}

- **Pass:** {PASS_COUNT}/{TOTAL_COUNT} requirements verified
- **Fail:** {FAIL_COUNT} (details below if any)
- **Uncovered:** {UNCOVERED_COUNT} (details below if any)

{IF_FAILURES}
### Failures
{FAILURE_LIST}
{END_IF}

{IF_UNCOVERED}
### Uncovered Requirements
These have no automated test. Decide whether to add a test or accept
the risk:
{UNCOVERED_LIST}
{END_IF}

## Visual Evidence

{VISUAL_LIST}

(Screenshots and GIFs of the feature in action — review these to
confirm the feature looks and feels right.)

## What to Check

These items need your judgment — automated tests can't evaluate them:

{MANUAL_CHECK_LIST}

### How to Check

{CHECK_INSTRUCTIONS}

(Step-by-step: which URL, what to click, what to look for.)

---

**Next steps:**
- If everything looks good → say "approved" and the pipeline continues
  to production hardening (review-swarm).
- If changes are needed → describe what to fix. The pipeline will
  make changes, re-verify, and present a fresh checkpoint showing
  only what changed.
