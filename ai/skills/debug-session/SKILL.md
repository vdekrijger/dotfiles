---
name: debug-session
description: Hypothesis-first debugging with domain knowledge base and post-mortem capture. Use when starting any debugging session, investigating bugs, or diagnosing unexpected behavior.
user_invocable: true
---

# Debug Session

A structured debugging skill that loads domain-specific context, enforces
hypothesis-first investigation with evidence gathering, and captures
post-mortems for future reference.

## Knowledge Base Location

All knowledge base files live at `~/.claude/power-user/debugging-kb/`.

## Phase 1: Context Load

Before investigating, load relevant domain knowledge:

1. Read `~/.claude/power-user/debugging-kb/INDEX.md`
2. Match the user's symptom description against the symptom -> domain mapping
3. Read the matched domain file(s) from `domains/`
4. Read recent post-mortems from `post-mortems/` that share the same domain
5. For any section with `Last verified` older than 30 days, flag it:
   "This information is from [date] and may be stale. I'll verify against
   current code before relying on it."

Present a brief summary to the user:
"Based on past sessions, here's what I know about [domain]:
- [Key architecture points]
- [Most common failure modes]
- [Where to look first]
- [Known red herrings to avoid]
[If any stale entries:] Some of this hasn't been verified recently — I'll
check against current code as we go."

If no domain matches, say so and proceed with a fresh investigation.
Create a new domain file at the end if this turns out to be a recurring area.

## Phase 2: Hypothesis Loop

This is the core of the skill. For EVERY hypothesis:

### Step 1: Form the hypothesis

State it clearly and specifically:

**Hypothesis**: [What you think is wrong and WHY you think so]

### Step 2: Identify evidence

Before touching ANY code, identify what evidence would confirm or deny
the hypothesis:

**Evidence needed**:
1. [Specific action — SQL query with exact text, log command, code path to read]
2. [Specific action]

**What would confirm**: [Expected result if hypothesis is correct]
**What would deny**: [Expected result if hypothesis is wrong]

### Step 3: Gather evidence collaboratively

Ask the user to help gather evidence you cannot gather yourself:
- SQL queries against production/staging ClickHouse
- Checking logs in Grafana, Sentry, or other external tools
- Hitting endpoints or reproducing behavior

For evidence you CAN gather (reading code, checking git history, running
local commands), do it yourself and report what you found.

Format: "Can you run #1 while I check #2?"

### Step 4: Evaluate and decide

- Evidence CONFIRMS hypothesis -> proceed to Phase 3 (Fix)
- Evidence DENIES hypothesis -> form a NEW hypothesis. Do NOT patch
  the old one. Explicitly state: "Hypothesis denied because [evidence].
  New hypothesis: ..."
- Evidence is AMBIGUOUS -> identify what additional evidence would
  disambiguate. Ask for it.

### Circuit breaker

After 3 denied hypotheses, STOP and say:
"I've had 3 hypotheses denied. I may be working from wrong assumptions
about how this system works. Let me re-read the relevant code paths from
scratch before forming another hypothesis."

Then do a fresh code read of the relevant subsystem before continuing.

## HARD RULES

- **No code changes until a hypothesis is confirmed with evidence.**
  No "let me just try this" or "quick fix to see if it helps."
- **No stacking hypotheses.** One at a time. Test it. Move on.
- **No skipping evidence gathering.** Even if you're "pretty sure,"
  identify and gather confirming evidence.
- **Always present what would DENY your hypothesis**, not just what
  would confirm it. This prevents confirmation bias.

## Phase 3: Fix

Once a hypothesis is confirmed with evidence, fix the root cause.
Follow systematic-debugging Phase 4 principles:

1. Create a failing test that reproduces the issue
2. Implement the minimal fix addressing the confirmed root cause
3. Verify the fix resolves the original symptom
4. Run the full relevant test suite

## Phase 4: Post-Mortem Capture

### Trigger

Prompt the user to capture a post-mortem when you detect they are
shifting away from debugging:
- They mention customer communication ("let me update the customer",
  "I'll write up the response", "let me ping them")
- They mention wrapping up ("ok that's it", "done", "thanks")
- They start a different task
- They explicitly say "post-mortem" or "wrap up"

Prompt: "Looks like we've resolved this — want me to capture the
post-mortem before we move on?"

### Capture process

If the user agrees:

1. Auto-generate a post-mortem following the template in
   `references/post-mortem-template.md`
2. Fill in ALL fields from the conversation:
   - Every hypothesis tested, with evidence and result
   - The confirmed root cause
   - The fix applied (with file:line references)
   - Red herrings encountered
   - "Next time, check X first" recommendation
3. Present the draft to the user for review
4. After approval, write to:
   `~/.claude/power-user/debugging-kb/post-mortems/YYYY-MM-DD-<slug>.md`
5. Update the relevant domain file:
   - Add any new failure modes discovered
   - Add any new red herrings discovered
   - Update "Where to look first" if the investigation revealed a
     better diagnostic order
   - Update `Last verified` dates on sections that proved accurate
   - Correct any sections that proved inaccurate
6. Update INDEX.md:
   - Add any new symptom -> domain mappings discovered
   - Add the post-mortem to the "Recent Post-Mortems" list

### If no domain file exists

If this debugging session covered a subsystem that doesn't have a domain
file yet, create one using the template in `references/domain-template.md`,
seeded with what was learned during this session. Add the domain to INDEX.md.
