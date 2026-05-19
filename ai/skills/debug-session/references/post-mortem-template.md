# Post-Mortem Template

Use this template when capturing a post-mortem at the end of a debugging session.

## File naming

`~/.claude/power-user/debugging-kb/post-mortems/YYYY-MM-DD-<slug>.md`

Where `<slug>` is a short kebab-case description (e.g., `export-timeout-large-dashboard`).

## Template

---
# [Title — short description of the issue]

**Date**: YYYY-MM-DD
**Domain**: [domain name matching a file in domains/]
**Duration**: [approximate time spent debugging]
**Severity**: [Customer-facing / Internal / Dev-only]

## Symptoms
- [Observable behavior that triggered the investigation]
- [Error messages, if any]

## Investigation Timeline
1. **Hypothesis**: [what we thought was wrong]
   - Evidence sought: [what we checked]
   - Result: [what we found] — CONFIRMED / DENIED
2. **Hypothesis**: [next theory]
   - Evidence sought: [what we checked]
   - Result: [what we found] — CONFIRMED / DENIED

## Root Cause
[Clear explanation of what was actually wrong and why]

## Fix
[What was changed, with file:line references]

## Red Herrings
- [Things that looked suspicious but were not the cause]

## Lessons Learned
- **Next time, check X first** — [actionable recommendation]
- [Any other insights about the subsystem]
---
