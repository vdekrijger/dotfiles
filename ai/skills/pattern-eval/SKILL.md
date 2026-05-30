---
name: pattern-eval
description: Analyze recent Claude Code sessions to identify anti-patterns in prompt quality and validation overhead. Generates HTML report and proposes configuration changes. Use manually or via weekly cron.
user_invocable: true
---

# Pattern Evaluation

Analyze recent Claude Code sessions to surface anti-patterns, track
improvement trends, and propose concrete changes to CLAUDE.md, memory,
and skills.

## Relationship with /insights

`/insights` produces a comprehensive usage profile covering the full
session history — interaction style, friction categories, feature
suggestions, and a polished HTML report.

`/pattern-eval` adds **weekly diff analysis** on top:
- Correction-level granularity (quoting exact user messages)
- One-shot rate tracking over time (trends.md)
- Specific prompt->outcome pairs (what phrasing worked vs didn't)
- Proposed CLAUDE.md/memory changes based on repeated corrections

The two are complementary: pattern-eval runs its own analysis, then
delegates the HTML report to `/insights`.

**Sibling: `pr-feedback-miner`.** This skill analyzes Claude Code
*sessions* for anti-patterns. `pr-feedback-miner` analyzes GitHub *PR
comments* for the same goal — surfacing recurring corrections and
feeding them into reviewer calibration. Run both: pattern-eval for
how you interact with the agent, pr-feedback-miner for what human
reviewers keep catching in PRs.

## Data Locations

Derive the project directory dynamically:
- Encode the current working directory as a path
  (e.g., `/Users/vasco/Developing/posthog` → `-Users-vasco-Developing-posthog`)
- Session data lives at `~/.claude/projects/{encoded}/`
- If the encoded path doesn't exist, glob `~/.claude/projects/` and
  pick the most recently modified directory

Specific files:
- Session index: `{project_dir}/sessions-index.json`
- Session logs: `{project_dir}/*.jsonl`
- Debugging post-mortems: `~/.claude/power-user/debugging-kb/post-mortems/`
- Previous evaluations: `~/.claude/power-user/patterns/evaluations/`
- Trends: `~/.claude/power-user/patterns/trends.md`
- Proposed changes log: `~/.claude/power-user/patterns/proposed-changes.md`

## Step 1: Session Extraction

Run the bundled parsing script:

```bash
python3 ~/.claude/skills/pattern-eval/references/parse_sessions.py \
  --project-dir {project_dir} \
  --since {cutoff_date}
```

Where `{cutoff_date}` is the date of the most recent evaluation in
`patterns/evaluations/`, or 7 days ago if no prior evaluation exists.

The script handles:
- Stale sessions-index.json (falls back to file mtime)
- False positive suppression (code review passthrough, meta messages)
- Trivial session detection (commands, version checks)
- Correction signal classification per `references/heuristics.md`

Output is JSON to stdout. Capture it for Step 2.

If the script fails or isn't available, fall back to manual JSONL
parsing using the heuristics in `references/heuristics.md`, but
follow the same false-positive mitigation rules documented there.

## Step 2: Pattern Detection

Analyze the parsed session data across two focus areas:

### A. Prompt Quality / One-Shot Rate (PRIMARY)

- Calculate one-shot rate using **non-trivial sessions only**
  (the script marks trivial sessions with `"trivial": true`)
- Report both rates: `one_shot_rate_all` and `one_shot_rate_non_trivial`
- Identify sessions that "struggled" (>5 exchanges or >=2 corrections)
- For struggling sessions, categorize the correction theme:
  - **Scope misunderstanding**: Claude built too much or too little
  - **Over-engineering**: Claude added unnecessary complexity
  - **Missing existing patterns**: Claude didn't follow codebase conventions
  - **Wrong approach**: Claude went down the wrong path entirely
- Extract specific prompt->outcome pairs: what phrasing worked well
  vs what led to corrections. Quote the actual messages.

### B. Trust/Validation Overhead (PRIMARY)

- Count sessions containing validation-request signals
  ("are you sure", "double check", "did you test")
- Identify patterns: does the user always re-verify certain types
  of work (e.g., always checks test output, always re-reads diffs)?
- Note cases where Claude could have self-validated but didn't
  (e.g., user asked "did you run the tests?" when Claude should
  have run them proactively)

### C. Debugging Efficiency (CONDITIONAL)

Only analyze this if debugging post-mortems exist in
`~/.claude/power-user/debugging-kb/post-mortems/` from the
evaluation period. If none exist, skip this section entirely —
do not report "no data" filler.

When post-mortems are available:
- Count hypotheses tested per session (from post-mortem timeline)
- Note sessions where >3 hypotheses were needed
- Track time-to-root-cause if duration is recorded

## Step 3: Report Generation

1. Save raw analysis data to:
   `~/.claude/power-user/patterns/evaluations/YYYY-MM-DD.md`

2. Update `~/.claude/power-user/patterns/trends.md` — append a new
   row with this week's metrics.

3. **MANDATORY: Invoke `/insights` via the Skill tool.**
   Do NOT generate HTML yourself. Do NOT skip this step.
   The `/insights` skill has deep context about session analysis
   and produces a richer, more comprehensive report than you can
   generate manually. Use `Skill(skill="insights")` to invoke it.
   It will produce the HTML report at `~/.claude/usage-data/report.html`.

   After `/insights` completes, continue to Step 4.
   The pattern-eval analysis (correction signals, one-shot rate,
   anti-patterns, best prompts) supplements the `/insights` report —
   present these findings inline in the conversation alongside the
   `/insights` report URL.

## Step 4: Proposed Changes (Interactive Mode Only)

Skip this step if running in non-interactive/cron mode (detect via
the absence of user input capability).

Based on detected patterns, propose concrete changes:

1. **CLAUDE.md additions**: If a correction theme repeats across
   multiple sessions, propose a new instruction. Example:
   "You corrected scope 4 times this week. Proposed CLAUDE.md addition:
   'When modifying existing code, default to the minimum change unless
   I explicitly ask for a broader refactor.'"

2. **Memory updates**: If a specific correction should persist as a
   feedback memory, propose it. Example:
   "You said 'don't mock the database' twice. Proposed feedback memory:
   'Integration tests must use real database, not mocks.'"

3. **Skill tweaks**: If a skill consistently produces work that gets
   rejected, flag it for review.

Present proposals as a numbered list. For each:
- Quote the evidence (actual session messages)
- Explain the proposed change
- Ask: accept or reject?

Apply accepted changes immediately (write to CLAUDE.md or memory files).
Log ALL proposals (accepted and rejected) with rationale to
`~/.claude/power-user/patterns/proposed-changes.md`.

## Cron Mode

When running via `launchd` cron (`claude -p "/pattern-eval"`):
- Execute steps 1-3 only (skip step 4 — no interactive proposals)
- `/insights` will write its HTML report to `~/.claude/usage-data/report.html`
- Log completion to `/tmp/claude-pattern-eval.log`
- The user reviews the report manually and can run `/pattern-eval`
  interactively to act on proposals
