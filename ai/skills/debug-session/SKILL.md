---
name: debug-session
description: Use when starting any debugging session, investigating bugs, or diagnosing unexpected behavior. Hypothesis-first debugging with a domain knowledge base and post-mortem capture.
user_invocable: true
---

# Debug Session

All knowledge base files live at `~/.claude/power-user/debugging-kb/`.

## Phase 1: Context Load

Before investigating:

1. Read `~/.claude/power-user/debugging-kb/INDEX.md`; match the symptom against the symptom -> domain mapping
2. Read matched domain file(s) from `domains/` and recent same-domain post-mortems from `post-mortems/`
3. Flag any section with `Last verified` older than 30 days: "This information is from [date] and may be stale. I'll verify against current code before relying on it."

Summarize briefly: key architecture points, common failure modes, where to look first, known red herrings, stale-entry caveat if any.

If no domain matches, say so and proceed fresh; create a domain file at the end if this is a recurring area.

## Phase 2: Hypothesis Loop

For EVERY hypothesis:

1. **Form it** specifically: "**Hypothesis**: [what's wrong and WHY you think so]"
2. **Identify evidence** before touching ANY code: **Evidence needed** (numbered specific actions — exact SQL text, log command, code path), **What would confirm**, **What would deny**
3. **Gather collaboratively**: ask the user for what you can't get (prod/staging SQL, Grafana/external logs, reproducing behavior); gather the rest yourself (code reads, git history, local commands) and report. Format: "Can you run #1 while I check #2?"
4. **Evaluate**: CONFIRMS -> Phase 3. DENIES -> NEW hypothesis, never patch the old one; state "Hypothesis denied because [evidence]. New hypothesis: ..." AMBIGUOUS -> identify what would disambiguate; ask for it.

**Circuit breaker**: after 3 denied hypotheses, STOP: "I've had 3 hypotheses denied. I may be working from wrong assumptions about how this system works. Let me re-read the relevant code paths from scratch before forming another hypothesis." Then do that fresh code read before continuing.

## HARD RULES

- **No code changes until a hypothesis is confirmed with evidence.** No "let me just try this."
- **No stacking hypotheses.** One at a time.
- **No skipping evidence gathering**, even when "pretty sure."
- **Always present what would DENY your hypothesis**, not just confirm — prevents confirmation bias.

## Phase 3: Fix

Once confirmed, fix the root cause (systematic-debugging Phase 4 principles): failing test that reproduces the issue, minimal fix for the confirmed root cause, verify the original symptom is resolved, run the full relevant test suite.

## Phase 4: Post-Mortem Capture

**Trigger**: when the user shifts away from debugging — mentions customer communication ("let me update the customer"), wrapping up ("ok that's it", "done", "thanks"), starts a different task, or says "post-mortem"/"wrap up" — prompt: "Looks like we've resolved this — want me to capture the post-mortem before we move on?"

If they agree:

1. Auto-generate a post-mortem from `references/post-mortem-template.md`, filling ALL fields from the conversation: every hypothesis with evidence and result, confirmed root cause, fix applied (file:line), red herrings, "Next time, check X first" recommendation
2. Present the draft; after approval, write to `~/.claude/power-user/debugging-kb/post-mortems/YYYY-MM-DD-<slug>.md`
3. Update the domain file: new failure modes and red herrings, better "Where to look first" order if one emerged, `Last verified` dates on sections that proved accurate, corrections to inaccurate sections
4. Update INDEX.md: new symptom -> domain mappings; add the post-mortem to "Recent Post-Mortems"

**If no domain file exists**, create one from `references/domain-template.md` seeded with this session's learnings, and add the domain to INDEX.md.
