---
name: pattern-eval
description: Use when analyzing recent Claude Code sessions for anti-patterns in prompt quality or validation overhead, when reviewing one-shot-rate or correction trends, or when invoked manually or by the weekly cron.
user_invocable: true
---

# Pattern Evaluation

Weekly diff analysis on top of `/insights` (full-history usage profile): correction-level granularity quoting exact user messages, one-shot rate tracking (trends.md), prompt->outcome pairs, proposed CLAUDE.md/memory changes from repeated corrections. Runs its own analysis, then delegates the HTML report to `/insights`. Sibling `pr-feedback-miner` does the same for GitHub PR comments — run both: sessions here, human PR feedback there.

## Data Locations

Derive the project dir: encode cwd (`/Users/vasco/Developing/posthog` → `-Users-vasco-Developing-posthog`); session data is `~/.claude/projects/{encoded}/`. If missing, glob `~/.claude/projects/` and take the most recently modified dir.

- Session index: `{project_dir}/sessions-index.json`
- Session logs: `{project_dir}/*.jsonl`
- Debugging post-mortems: `~/.claude/power-user/debugging-kb/post-mortems/`
- Previous evaluations: `~/.claude/power-user/patterns/evaluations/`
- Trends: `~/.claude/power-user/patterns/trends.md`
- Proposed changes log: `~/.claude/power-user/patterns/proposed-changes.md`

## Step 1: Session Extraction

```bash
python3 ~/.claude/skills/pattern-eval/references/parse_sessions.py \
  --project-dir {project_dir} \
  --since {cutoff_date}
```

`{cutoff_date}` = date of the most recent evaluation in `patterns/evaluations/`, else 7 days ago. The script handles stale sessions-index.json (mtime fallback), false-positive suppression (code review passthrough, meta messages), trivial session detection (commands, version checks), and correction-signal classification per `references/heuristics.md`. Output is JSON on stdout — capture for Step 2. If the script fails, fall back to manual JSONL parsing with `references/heuristics.md`, following the same false-positive mitigation rules.

## Step 2: Pattern Detection

### A. Prompt Quality / One-Shot Rate (PRIMARY)

- One-shot rate from **non-trivial sessions only** (script marks `"trivial": true`); report both `one_shot_rate_all` and `one_shot_rate_non_trivial`
- "Struggling" sessions (>5 exchanges or >=2 corrections): categorize the correction theme — **Scope misunderstanding** (too much/too little), **Over-engineering**, **Missing existing patterns** (codebase conventions), **Wrong approach**
- Extract prompt->outcome pairs — phrasing that worked vs led to corrections, quoting actual messages

### B. Trust/Validation Overhead (PRIMARY)

- Count sessions with validation-request signals ("are you sure", "double check", "did you test")
- Does the user always re-verify certain work types (test output, diffs)?
- Note where Claude could have self-validated but didn't (e.g. should have run tests proactively instead of being asked)

### C. Debugging Efficiency (CONDITIONAL)

Only if `~/.claude/power-user/debugging-kb/post-mortems/` has post-mortems from the evaluation period; otherwise skip entirely — no "no data" filler. When available: hypotheses tested per session (post-mortem timeline), sessions needing >3 hypotheses, time-to-root-cause if recorded.

## Step 3: Report Generation

1. Save raw analysis to `~/.claude/power-user/patterns/evaluations/YYYY-MM-DD.md`
2. Append this week's metrics row to `~/.claude/power-user/patterns/trends.md`
3. **MANDATORY: invoke `/insights` via `Skill(skill="insights")`.** Do NOT generate HTML yourself or skip this — `/insights` produces a richer report, at `~/.claude/usage-data/report.html`. Afterwards, present the pattern-eval findings (correction signals, one-shot rate, anti-patterns, best prompts) inline alongside the `/insights` report URL, then continue to Step 4.

## Step 4: Proposed Changes (Interactive Mode Only)

Skip in non-interactive/cron mode (no user input capability). Propose concrete changes:

1. **CLAUDE.md additions** — a correction theme repeating across sessions becomes a proposed instruction (e.g. 4 scope corrections → "default to the minimum change unless I explicitly ask for a broader refactor")
2. **Memory updates** — a correction worth persisting becomes a proposed feedback memory (e.g. "don't mock the database" twice → "Integration tests must use real database, not mocks")
3. **Skill tweaks** — flag any skill whose output consistently gets rejected

Present as a numbered list: quote the evidence (actual session messages), explain the change, ask accept or reject. Apply accepted changes immediately (CLAUDE.md or memory files). Log ALL proposals — accepted and rejected — with rationale to `~/.claude/power-user/patterns/proposed-changes.md`.

## Cron Mode

Via `launchd` cron (`claude -p "/pattern-eval"`): run steps 1-3 only (skip step 4); `/insights` writes `~/.claude/usage-data/report.html`; log completion to `/tmp/claude-pattern-eval.log`. The user reviews the report manually and runs `/pattern-eval` interactively to act on proposals.
