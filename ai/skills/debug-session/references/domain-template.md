# Domain File Template

Use this template when creating a new domain file or updating sections of an existing one.

## File location

`~/.claude/power-user/debugging-kb/domains/<domain-name>.md`

## Template

---
# [Domain Name]

## Architecture
> Last verified: YYYY-MM-DD

[How the subsystem works: entry points, key files, data flow, dependencies]

## Common Failure Modes
> Last verified: YYYY-MM-DD

[Known ways this subsystem breaks, with symptoms and typical causes]

## Where to Look First
> Last verified: YYYY-MM-DD

[Ordered checklist: most likely causes first, with specific file paths,
SQL queries, log commands, or other diagnostic steps]

## Red Herrings
> Last verified: YYYY-MM-DD

[Things that look like the problem but usually are not]
---

## Staleness rules

- Every section has a `> Last verified: YYYY-MM-DD` blockquote
- When you use information from a section during debugging and it proves accurate,
  update the date to today
- When information proves inaccurate, correct it immediately and update the date
- Entries older than 30 days should be treated as "may be stale" and verified
  against current code before relying on them
