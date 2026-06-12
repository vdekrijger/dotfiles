---
name: pr-feedback-miner
description: Use when mining human PR feedback (GitHub review comments, PR comments, applied suggestions) into reviewer calibration — after a PR lands with comments, for periodic bulk scans, or before a review-swarm calibration refresh.
user_invocable: true
---

# PR Feedback Miner

Closes the learning loop: human PR feedback → classification → reviewer calibration → fewer repeats. Review-swarm calibration learns from FP/wins reported within swarm runs; this skill adds the missing half — human PR feedback that never went through the swarm.

## When to Run

- **After a PR lands with human feedback** (primary): each merged PR with reviewer comments.
- **Periodic bulk run**: scan the last N merged PRs for systemic gaps.
- **Before a major review-swarm calibration refresh**: bulk-feed recent human patterns into the calibration files.

## Pipeline

1. Discover PRs → 2. Fetch feedback (review comments + PR comments + applied suggestions) → 3. Classify → reviewer patterns → 4. Generate calibration entries (calibration.md / wins.md) → 5. Report + propose vasco-reviewer updates

## Step 1: Discover PRs

```
pr-feedback-miner --repo <owner/name> --pr <number>                          # single PR
pr-feedback-miner --repo <owner/name> --since 2026-05-01 --until 2026-05-28  # date range
pr-feedback-miner --local --since 2026-05-01                                 # current repo
```

Local mode: derive `--repo` from `git remote get-url origin`, scan PRs authored by the local user's GitHub handle.

## Step 2: Fetch Feedback

Use `gh` (handles auth, pagination, rate limiting):

```bash
gh pr view <number> --repo <owner/name> --json number,title,author,state,mergedAt,reviews  # metadata
gh api repos/<owner>/<name>/issues/<number>/comments --paginate    # PR comments (top-level)
gh pr view <number> --repo <owner/name> --json reviewComments      # inline diff comments
# Applied suggestions: search "suggestion" in review comments (reviews have `body`; review comments have `diff_hunk` + `body`)
```

Filter to **actionable human feedback only**:

| Include | Exclude |
|---------|---------|
| Review comments from humans (`author_association != 'NONE'` and not bot) | Bot comments (dependabot, codecov, linter bots) |
| PR comments that are corrections/requests | CI status comments, deploy previews |
| Applied suggestions (comment resolved + code changed) | "+1", "LGTM", approval stamps |
| Threads where the PR author responded with a fix | Off-topic discussion |

Store the raw feedback in a temp JSON file for classification.

## Step 3: Classify Feedback

Classify each item against the **vasco-reviewer priority list** (detailed matching rules: `references/classification-rules.md`):

| Priority | Pattern |
|----------|---------|
| 1. Tests: edge cases | Missing None/empty/error tests ("add a test for when this returns null?") |
| 2. Tests: parameterization | Repeated test bodies |
| 3. Tests: meaningful assertions | Tests that would pass with an empty implementation |
| 4. Scope discipline | Unrelated changes ("why did this file get regenerated?") |
| 5. Constants over magic strings | String literal vs enum ("use OrderStatus.PENDING") |
| 6. Shared helpers | Duplicated logic across call sites |
| 7. Refactor hygiene | Stale references, shims ("renamed X but forgot this import") |
| 8. Python type annotations | Missing types |
| 9. Naming/readability | Boolean inversions, double negatives |
| 10. Coupling | Index/ordering-based coupling |

Also detect **new patterns** — corrections matching no existing priority; candidates for new vasco-reviewer priorities.

Output a JSON classification file: `pr_number`, `comment_url`, `comment_author`, `comment_body`, `classified_as` (priority number + label), `was_applied`, `is_new_pattern`, `suggested_priority` (proposed entry, for new patterns).

## Step 4: Generate Calibration Entries

**`calibration.md` (false positives):** feedback where the human pushed back on something a reviewer would plausibly flag, or said something ISN'T a problem. Rare from PR comments.

**`wins.md` (confirmed catches — primary output):** every applied human correction matching a vasco-reviewer priority becomes a WIN entry — the swarm should keep raising it. Format (matches review-swarm wins.md):

```
## YYYY-MM-DD — <repo-slug> — pr-feedback-miner
- Finding (<reviewer>, <severity>): <classification>
  Location: PR #<N>, <comment_url>
  Marked WIN. Note: Human reviewer <author> caught this. Applied: <yes/no>
```

**Severity mapping**:

| Feedback applied? | Multiple instances? | Severity |
|-------------------|---------------------|----------|
| Yes | 3+ across PRs | HIGH |
| Yes | 2 across PRs | MEDIUM |
| Yes | Single instance | LOW |
| No (suggestion not applied) | Any | NIT (not a win) |

## Step 5: Report + Propose Updates

Write a markdown report to `~/.claude/skills/review-swarm/references/miner-reports/YYYY-MM-DD.md` with sections:

- **Scope**: repo, PRs analyzed (+ since date), comments reviewed, actionable count, applied count, new patterns detected
- **Pattern Distribution**: table of priority | count | applied
- **Top Missed Patterns**: ranked list of what humans catch that the swarm missed — counts plus the most common concrete cases
- **Proposed Calibration Updates**: new entry counts for calibration.md and wins.md, proposed vasco-reviewer SKILL.md changes
- **New Pattern Candidates**: per candidate — instance count across PRs, description, proposed priority entry (or, if already present, a note to elevate it due to frequency)

### Appending to calibration files

After presenting the report, ask before writing:

```
[pr-feedback-miner] Ready to apply:
  - Append <N> WIN entries to review-swarm/references/wins.md
  - <N> new FP entries for calibration.md

  Proposed vasco-reviewer SKILL.md changes:
  - <each proposed priority addition>

  Apply all? [y/N/select]:
```

On confirmation, append to the calibration files and patch vasco-reviewer SKILL.md. The next review-swarm run automatically picks up new entries (Stage 2 reads the last 10 entries per reviewer from both files).

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

Weekly cron (Monday mornings — scans last week's PRs, auto-applies, reports):

```
hermes cron create \
  --name "PR feedback miner (weekly)" \
  --schedule "0 9 * * 1" \
  --skills pr-feedback-miner \
  --prompt "Run pr-feedback-miner --local --since last-week --auto-apply --limit 30 against the PostHog repo at ~/work/posthog. Report findings to the Home channel."
```

Post-merge trigger (immediate feedback after a PR lands): `pr-feedback-miner --local --pr <just-merged-number>`

## Rules

- **Never modify calibration files without human confirmation** unless `--auto-apply` is set.
- **Respect PR privacy.** Summarize patterns; never quote full comment bodies in reports.
- **Don't over-weight single instances.** Require 2+ instances before proposing a new vasco-reviewer priority.
- **Bot comments are noise.** Filter aggressively: known bots (dependabot, codecov, etc.) and CI-artifact-only comments.
- **The human is the final arbiter.** The miner proposes; the human decides what becomes calibration.

## Pitfalls

- **Discovery: prefer REST over GraphQL.** `gh search prs` (GraphQL) can fail with auth/permission errors on private/restricted repos; the script uses `gh pr list --search` (REST). If that also fails, fall back to `gh pr list --state merged --limit N` and filter by author client-side.
- **Self-review comments are noise.** Agent-authored PRs carry lengthy author self-review comments; the script filters `login == pr_author`. Without this, scans on agent-authored PRs are 80%+ self-review noise.
- **User-corrections-on-agent-code are a separate category.** The user commenting on agent-authored PRs (e.g. "simplify verbose comments") IS calibration-worthy — but the commenter is the PR author, so the script must detect it separately from external human review. These eventually feed vasco-reviewer priorities (e.g. #14 Comment discipline) and the miner catches them on future runs.
