# Pattern Detection Heuristics

## Session JSONL Parsing

Session logs are at `~/.claude/projects/-Users-vasco-Developing-posthog/`.
The `sessions-index.json` file contains metadata for all sessions.

### Relevant JSONL entry types

- `type: "user"` with `isMeta: false` — user messages
- `type: "assistant"` — Claude responses (content is array of objects,
  filter to `type: "text"` entries)
- Skip: `type: "progress"`, `type: "file-history-snapshot"`,
  `isMeta: true` entries (hook events, skill injection, system messages)

### Message content formats

User messages: `entry.message.content` is either:
- A string (direct text)
- An array of `{type: "text", text: "..."}` objects

Assistant messages: `entry.message.content` is an array, filter to
`{type: "text", text: "..."}` entries (skip `type: "thinking"`,
`type: "tool_use"`, etc.)

## Correction Signal Detection

Apply these regex patterns to user messages to detect corrections:

### Direct negation (high confidence)
- `^no[,.\s!]` — message starts with "no"
- `\bnot that\b` — explicit rejection
- `\bwrong\b` — explicit rejection
- `\bstop\b` — explicit stop

### Redirection (high confidence)
- `\bI meant\b` — user clarifying intent
- `\bI said\b` — user repeating themselves
- `\bwhat I want\b` — user re-explaining
- `\binstead\b` — user redirecting approach

### Frustration (medium confidence, check context)
- `\bagain\b` — may indicate repetition (but also "run again")
- `\balready told you\b` — repeated instruction
- `\bI just said\b` — repeated instruction

### Scope correction (medium confidence)
- `\btoo much\b` — over-engineering signal
- `\bover.?engineer\b` — explicit over-engineering call-out
- `\bjust the\b` — scope narrowing
- `\bonly\b` near start of message — scope limiting

### Validation request (low-medium confidence)
- `\bare you sure\b` — trust gap
- `\bdouble.?check\b` — trust gap
- `\bverify\b` near start — trust gap
- `\bdid you test\b` — trust gap

## False Positive Mitigation

The correction patterns above produce false positives in common
workflows. Apply these suppressors before counting a signal:

### Code review passthrough

When the user pastes code review feedback verbatim, the review text
often contains words like "instead", "wrong", "not that", "stop" —
but these are the *reviewer's* words, not user corrections.

**Suppress signals** when the message contains any of:
- `"This is a comment left during a code review"`
- `"Comment:"` near the start (within first 300 chars)
- `"Path:"` + `"Line:"` pattern (structured review comment)
- Bold markdown (`**`) in first 200 chars (review finding headers)

### Meta / command messages

Messages starting with XML-like tags are system injections, not
user corrections:
- `<command-name>` — slash command invocation
- `<command-message>` — command payload
- `<task-notification>` — background task result

**Skip these entirely** — don't count as user messages at all.

### Multi-topic "instead"

In long exploratory sessions, "instead" often signals a topic shift
rather than a correction. To reduce false positives:
- If the message is >500 chars and contains "instead" only once,
  check whether the surrounding context is a new question vs a
  redirection of Claude's last response
- Messages starting with "Hi", "Quick Q", "got a question" followed
  by "instead" are topic shifts, not corrections

### "verify" at the start

`\bverify\b` near the start of a message can be a user asking Claude
to verify *their own* code, not expressing distrust. Only count as
a validation_request if the message also references Claude's prior
output ("you said", "your", "the change", "that").

## One-Shot Classification

Count user messages (non-meta) per logical task within a session:
- **Trivial**: ≤1 user message OR first prompt <50 chars and matches
  trivial keywords (version, test, /clear, command invocations).
  Trivial sessions are excluded from one-shot rate calculations.
- **One-shot (non-trivial)**: task completed in ≤2 user messages
  AND not trivial
- **Multi-round**: 3-5 exchanges
- **Struggling**: >5 exchanges OR contains ≥2 correction signals

## Task Boundary Detection

A "task" within a session is bounded by:
- Session start/end
- Clear topic shifts (user starts talking about something unrelated)
- Explicit task markers ("now let's...", "next:", "moving on to...")

This is approximate — for v1, treat each session as one task unless
it's clearly multi-task (>30 messages with distinct topic shifts).
