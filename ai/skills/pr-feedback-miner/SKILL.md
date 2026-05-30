---
name: pr-feedback-miner
description: Mines human PR feedback (review comments, PR comments, applied suggestions) from GitHub and converts them into structured reviewer improvements — vasco-reviewer priority updates, review-swarm calibration entries, and pattern detection. Closes the learning loop between human corrections and automated reviewer calibration.
user_invocable: true
---

# PR Feedback Miner

Closes the learning loop: human PR feedback → classification → reviewer calibration → fewer repeats.

The review-swarm calibration system learns from FP/wins reported *within* swarm runs. This
skill adds the missing half — learning from external human PR feedback that never went through
the swarm at all. Every time a human reviewer catches something the swarm missed, that signal
should feed back into the calibration system so it doesn't get missed again.

## When to Run

- **After a PR lands with human feedback** — the primary use case. Run on each merged PR that
  received reviewer comments to extract patterns.
- **Periodic bulk run** — scan the last N merged PRs to identify systemic gaps.
- **Before a major review-swarm calibration refresh** — bulk-feed recent human patterns into
  the calibration files before a new development cycle.

## Pipeline

```
1. Discover PRs
     ↓
2. Fetch feedback (review comments + PR comments + applied suggestions)
     ↓
3. Classify feedback → reviewer patterns
     ↓
4. Generate calibration entries (calibration.md / wins.md)
     ↓
5. Report + propose vasco-reviewer updates
```

## Step 1: Discover PRs

Three modes, selected by the invoker:

### Single PR mode
```
pr-feedback-miner --repo <owner/name> --pr <number>
```

### Date-range mode
```
pr-feedback-miner --repo <owner/name> --since 2026-05-01 --until 2026-05-28
```

### Local mode (current repo + branch heuristics)
```
pr-feedback-miner --local --since 2026-05-01
```

In local mode, derive `--repo` from `git remote get-url origin` and scan PRs where the
local user's GitHub handle appears as the author.

## Step 2: Fetch Feedback

Use the GitHub CLI (`gh`) — it handles auth, pagination, and rate limiting:

```bash
# PR metadata (who reviewed, merge status)
gh pr view <number> --repo <owner/name> --json number,title,author,state,mergedAt,reviews

# PR comments (top-level conversation)
gh api repos/<owner>/<name>/issues/<number>/comments --paginate

# Review comments (inline diff comments)
gh pr view <number> --repo <owner/name> --json reviewComments

# Applied suggestions (search for "suggestion" in review comments)
# Reviews contain a `body` field; review comments have `diff_hunk` + `body`
```

Filter to **actionable human feedback only**:

| Include | Exclude |
|---------|---------|
| Review comments from humans (`author_association != 'NONE'` and not bot) | Bot comments (dependabot, codecov, linter bots) |
| PR comments that are corrections/requests | CI status comments, deploy previews |
| Applied suggestions (comment marked as resolved + code changed) | "+1", "LGTM", approval stamps |
| Threads where the PR author responded with a fix | Off-topic discussion |

Store the raw feedback in a temp JSON file for the classification step.

## Step 3: Classify Feedback

For each piece of human feedback, classify it against the **vasco-reviewer priority list**
(see `references/classification-rules.md` for detailed matching rules):

| Priority | Pattern | Example human comment |
|----------|---------|----------------------|
| 1. Tests: edge cases | Missing None/empty/error tests | "Can you add a test for when this returns null?" |
| 2. Tests: parameterization | Repeated test bodies | "These three tests are basically the same" |
| 3. Tests: meaningful assertions | Assertions that test nothing | "This test would pass with an empty implementation" |
| 4. Scope discipline | Unrelated changes | "Why did this file get regenerated?" |
| 5. Constants over magic strings | String literal vs enum | "Use OrderStatus.PENDING here" |
| 6. Shared helpers | Duplicated logic | "This same validation is in three places" |
| 7. Refactor hygiene | Stale references, shims | "You renamed X but forgot this import" |
| 8. Python type annotations | Missing types | "Return type annotation please" |
| 9. Naming/readability | Boolean inversions etc. | "isNotReady is a double negative" |
| 10. Coupling | Index-based coupling | "Don't rely on array ordering" |

Also detect **new patterns** — corrections that don't match any existing priority. These are
candidates for new vasco-reviewer priorities.

Output a JSON classification file with:
- `pr_number`, `comment_url`, `comment_author`, `comment_body`
- `classified_as`: priority number + label
- `was_applied`: whether the PR author made the requested change
- `is_new_pattern`: true if it didn't match any existing priority
- `suggested_priority`: for new patterns, a proposed new priority entry

## Step 4: Generate Calibration Entries

From the classified feedback, produce two types of entries for the review-swarm calibration
system:

### For `calibration.md` (false positives — things the swarm might wrongly flag)

These come from feedback where the human *pushed back* on something a reviewer would
plausibly flag, or where the human explicitly said something ISN'T a problem. Less common
from PR comments but possible.

### For `wins.md` (confirmed catches — things the swarm SHOULD flag)

These are the primary output. Every applied human correction that matches a vasco-reviewer
priority becomes a WIN entry — the human confirmed it's a real issue, so the swarm should
keep raising this pattern.

Format (matches review-swarm wins.md format):

```
## YYYY-MM-DD — <repo-slug> — pr-feedback-miner
- Finding (<reviewer>, <severity>): <classification>
  Location: PR #<N>, <comment_url>
  Marked WIN. Note: Human reviewer <author> caught this. Applied: <yes/no>
```

**Severity mapping** from applied feedback to swarm severity:

| Feedback applied? | Multiple instances? | Severity |
|-------------------|---------------------|----------|
| Yes | 3+ across PRs | HIGH |
| Yes | 2 across PRs | MEDIUM |
| Yes | Single instance | LOW |
| No (suggestion not applied) | Any | NIT (not a win) |

## Step 5: Report + Propose Updates

### Report output

Write a markdown report to `~/.claude/skills/review-swarm/references/miner-reports/YYYY-MM-DD.md`:

```markdown
# PR Feedback Miner Report — 2026-05-29

## Scope
- Repo: posthog/posthog
- PRs analyzed: 15 (since 2026-05-01)
- Human comments reviewed: 87
- Actionable feedback: 42
- Applied corrections: 31
- New patterns detected: 2

## Pattern Distribution
| Priority | Count | Applied |
|----------|-------|---------|
| 4. Scope discipline | 12 | 10 |
| 5. Constants over magic strings | 8 | 7 |
| 7. Refactor hygiene | 6 | 5 |
| 1. Tests: edge cases | 5 | 4 |
| New: Temporal activity payload size | 3 | 3 |
| ... | | |

## Top Missed Patterns (things humans catch that swarm missed)
1. **Scope discipline (12 instances)** — 10 applied. Most common: accidentally-regenerated
   generated files, DRF serializer changes that regenerated OpenAPI types.
2. **Constants over magic strings (8 instances)** — 7 applied. Consistently catching
   `NodeKind` string literals in new code.

## Proposed Calibration Updates
- `calibration.md`: 0 new entries
- `wins.md`: 31 new entries (ready to append)
- `vasco-reviewer/SKILL.md`: 2 proposed priority additions (see below)

## New Pattern Candidates
### Pattern: Temporal activity payload size
3 instances across 3 PRs. Human reviewers flagged unbounded dataclass fields used as
Temporal activity I/O. Proposed vasco-reviewer priority: already present (PostHog section
#13). Add as **elevated priority** due to frequency.

### Pattern: Test file naming conventions
2 instances. Tests placed in wrong directory or misnamed relative to source. Not in
vasco-reviewer yet. Proposed priority 14: "Test file placement — test file names and
directories must match source module structure."
```

### Appending to calibration files

After presenting the report, ask the human before writing:

```
[pr-feedback-miner] Ready to apply:
  - Append 31 WIN entries to review-swarm/references/wins.md
  - No new FP entries for calibration.md

  Proposed vasco-reviewer SKILL.md changes:
  - Add priority 14: "Test file placement"

  Apply all? [y/N/select]:
```

On confirmation, append to the calibration files and patch vasco-reviewer SKILL.md.

### Integration with review-swarm

After calibration files are updated, the next review-swarm run automatically picks up
the new entries (Stage 2 reads the last 10 entries per reviewer from both files).

## Flags

```
--repo <owner/name>     GitHub repo (required unless --local)
--pr <number>           Single PR mode
--since <date>          Start date for PR discovery
--until <date>          End date (default: now)
--local                 Derive repo from git remote
--dry-run               Classify and report, don't write calibration files
--auto-apply            Skip confirmation prompt (for cron/automated use)
--limit <N>             Max PRs to scan (default: 20)
```

## Automation

### Cron job (weekly)

```
hermes cron create \
  --name "PR feedback miner (weekly)" \
  --schedule "0 9 * * 1" \
  --skills pr-feedback-miner \
  --prompt "Run pr-feedback-miner --local --since last-week --auto-apply --limit 30 against the PostHog repo at ~/work/posthog. Report findings to the Home channel."
```

This runs every Monday morning, scans the last week's PRs, auto-applies calibration
updates, and reports what changed.

### Post-merge trigger

For immediate feedback, run manually after a PR lands:
```
pr-feedback-miner --local --pr <just-merged-number>
```

## Rules

- **Never modify calibration files without human confirmation** unless `--auto-apply` is set.
- **Respect PR privacy.** Don't quote full comment bodies in reports — summarize patterns.
- **Don't over-weight single instances.** A comment from one reviewer on one PR is not a
  pattern. Require 2+ instances before proposing a new vasco-reviewer priority.
- **Bot comments are noise.** Filter aggressively. If the comment author is a known bot
  (dependabot, codecov, etc.) or the comment contains only CI artifacts, skip it.
- **The human is the final arbiter.** The miner proposes; the human decides what becomes
  calibration.

## Pitfalls

### Discovery API: prefer REST over GraphQL

`gh search prs` uses GitHub's GraphQL API, which can fail with auth/permission errors on
private repos or repos with restricted API access. The script now uses `gh pr list --search`
(REST API) instead. If the REST endpoint also fails, fall back to manual discovery: list
recent merged PRs with `gh pr list --state merged --limit N` and filter by author
client-side.

### Self-review comments are noise, not signal

Agent-authored PRs (like those from Claude Code / Hermes) often contain lengthy self-review
comments from the PR author explaining design decisions. These are the agent talking to
itself — not human corrections worth calibrating on. The script filters out comments from
the PR author (`login == pr_author`). Without this filter, a 14-day scan on agent-authored
PRs produces 80%+ self-review noise that buries the real human feedback.

### Verbose comment pattern is self-correcting

When the user tells the agent to simplify verbose comments across multiple agent-authored
PRs, that IS a pattern worth capturing — but the commenter is the PR author (the agent's
user telling the agent to fix the code). These are calibration-worthy but require the
script to detect them as a separate category: user-corrections-on-agent-code, not
external-human-review. In practice, these corrections eventually feed into vasco-reviewer
priorities (e.g. #14 Comment discipline) and the miner catches them on future runs.
